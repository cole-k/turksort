import time
import boto3
import random
from pprint import pprint
from xml.dom.minidom import parseString

# How long to wait between polling for a response from mturk
wait_time = 5
# Whether to print debug messages
debug = True
# Duration workers have to complete the task
assignment_duration = 300
# Duration the task is live
assignment_lifetime = 900

# Production
production = True

if production:
    # Prod
    endpoint_url = 'https://mturk-requester.us-east-1.amazonaws.com'
else:
    # Sandbox
    endpoint_url = 'https://mturk-requester-sandbox.us-east-1.amazonaws.com'

# Format item -- Description
#           n -- Index (0-based)
#           m -- Index (1-based, equal to n + 1)
#        left -- Left side of comparison
#       right -- Right side of comparison
button_group = \
'''
        <div id="div{n}">
          <h3> Question {m} </h3>

          <span> Which is <strong>greater</strong>?</span>
          <br>
          <crowd-radio-group>
            <crowd-radio-button name="left.{n}">{left}</crowd-radio-button>
            <br>
            <crowd-radio-button name="right.{n}">{right}</crowd-radio-button>
            <br>
            <crowd-radio-button name="equal.{n}">Neither</crowd-radio-button>
          </crowd-radio-group>
        </div>

'''

def to_bool(string):
    if string.lower() == 'false':
        return False
    if string.lower() == 'true':
        return True
    return None

def getAnswerContents(answerNode):
    [fieldNode]   = answerNode.getElementsByTagName('QuestionIdentifier')
    [answerNode]  = answerNode.getElementsByTagName('FreeText')
    field, answer = (n.firstChild.nodeValue for n in [fieldNode, answerNode])
    fieldType, fieldNumber, _ = field.split('.')
    return int(fieldNumber), fieldType, to_bool(answer)

def turk_compare_greater(queries):
    '''
    Compares a list of (x,y) queries via Amazon Mechanical Turk, returning
    whether x ('left'), y ('right'), or neither ('equal') is greater.

    Returns the list of answers as well as a value to indicate what reward was given.
    '''
    answers = [ None for _ in queries ]

    # start at 2 cents; scale for every 5 questions by 1 cent
    # cap at 10 cents
    reward = min(((len(queries) // 5) + 2) * 0.01, 0.10)

    with open('form-template.xml', 'r') as f:
        form = f.read()
        contents = ''
        for n, (x,y) in enumerate(queries):
            contents += button_group.format(n=n, m=n+1,left=str(x), right=str(y))
        question = form.format(contents)

    response = client.create_hit(
        MaxAssignments=1,
        LifetimeInSeconds=assignment_lifetime,
        AssignmentDurationInSeconds=assignment_duration,
        Reward='{:.2f}'.format(reward),
        Title='Which of these two objects is greater?',
        Keywords='quick, easy, question, answer, compare',
        Description='For each pair, pick which of the two is greater.',
        Question=question,
        QualificationRequirements=[],
    )

    # Poll every 'wait_time' seconds to see if there's a response
    hit_id = response['HIT']['HITId']
    if debug:
        print('Created HIT with id: {}.'.format(hit_id))
        print('View the hit at https://{}.mturk.com/mturk/preview?groupId={}'.format(
            'www' if production else 'workersandbox',
            response['HIT']['HITTypeId']))
        print('Waiting on a response',end='',flush=True)
    while True:
        if debug:
            print('.',end='',flush=True)
        time.sleep(wait_time)
        assignments_response = client.list_assignments_for_hit(
            HITId=hit_id,
            AssignmentStatuses=['Submitted', 'Approved']
        )
        if assignments_response['NumResults'] >= 1:
            break

    # Extract the answer
    assignment = assignments_response['Assignments'][0]
    contents = parseString(assignment['Answer'])
    for node in contents.getElementsByTagName('Answer'):
        n, field, isCorrect = getAnswerContents(node)
        if isCorrect:
            answers[n] = field
    if assignment['AssignmentStatus'] == 'Submitted' and all(answer is not None for answer in answers):
        client.approve_assignment(
            AssignmentId=assignment['AssignmentId'],
            RequesterFeedback='Thank you!',
            OverrideRejection=False
        )
    else:
        if debug:
            print()
            print('Turker did not fill all entries, rejecting and retrying.')
        client.reject_assignment(
            AssignmentId=assignment['AssignmentId'],
            RequesterFeedback='You did not answer all the questions :(',
        )
        # try again
        return turk_compare_greater(queries)
    # Add a newline to the debug prints
    if debug:
        print()
    return answers, reward

def computer_compare_greater(queries):
    '''
    Compares the queries in the same manner as 'turk_compare_greater', but
    limited by Python's type system.

    Returns 0 as the second argument to be congruous with the return type
    of 'turk_compare_greater' (it costs 0 cents to compare)
    '''
    answers = queries.copy()
    for i,(x, y) in enumerate(queries):
        if x > y:
            answers[i] = 'left'
        elif x < y:
            answers[i] = 'right'
        else:
            answers[i] = 'equal'
    return answers,0

def turksort(xs, compare_greater = turk_compare_greater):
    '''
    Sorts any array whose elements can be displayed for comparison.

    Returns the sorted array as well as the total cost.

    Simplicity favored over speed and memory usage, as well as the
    number of queries made.
    '''

    if len(xs) <= 1:
        return xs, 0

    pivot, *rest = xs

    queries = [ (pivot, x) for x in rest ]

    answers, cost = compare_greater(queries)

    if debug:
        print('Pivot: {}, array: {}, answers: {}'.format(pivot, rest, answers))

    lesser  = [ x for i, x in enumerate(rest) if answers[i] == 'left' ]
    equal   = [ pivot ] + [ x for i, x in enumerate(rest) if answers[i] == 'equal' ]
    greater = [ x for i, x in enumerate(rest) if answers[i] == 'right' ]

    lesser_sorted, lesser_cost = turksort(lesser, compare_greater)
    greater_sorted, greater_cost = turksort(greater, compare_greater)

    return  lesser_sorted + equal + greater_sorted, cost + lesser_cost + greater_cost


def test_computer_sort(sort, num_iterations=1000, max_int=1000, list_size=1000):
    print('Testing sort...')
    for _ in range(num_iterations):
        xs = random.sample(range(max_int),list_size)
        if any( x != y for x,y in zip(sort(xs), sorted(xs)) ):
            print('Sort failed on list {}'.format(xs))
            break
    else:
        print('Ran {} tests successfully'.format(num_iterations))

def test_weight():
    correct_order = [ 'half a pound of wheat'
                    , 'one pound of wheat'
                    , 'three pounds of lettuce'
                    , 'three pounds of feathers'
                    , 'nine pounds of hay'
                    , 'twenty pounds of rice'
                    , 'one ton of feathers'
                    , 'one ton of bricks'
                    ]
    queries = correct_order.copy()
    random.shuffle(queries)
    print('Input:')
    pprint(queries)
    print('Desired sorting:')
    pprint(correct_order)
    print('Computer sorted (lexicographic):')
    pprint(list(sorted(queries)))
    turksorted, cost = turksort(queries)
    print('Turksorted with cost {}:'.format(cost))
    pprint(turksorted)

if __name__ == '__main__':
    # test_computer_sort(lambda xs: turksort(xs, compare_greater = computer_compare_greater))
    session = boto3.Session()
    if production:
        print('!!! Running in production !!!')
        print('Cancel now if this was mistaken')
        time.sleep(10)
    client = session.client(
        service_name='mturk',
        endpoint_url=endpoint_url
    )
    test_weight()
