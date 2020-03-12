import csv
import time
import boto3
import random
from pprint import pprint
from xml.dom.minidom import parseString

# How long to wait between polling for a response from mturk
wait_time = 5
# Whether to print debug messages
debug = False
# Duration workers have to complete the task
assignment_duration = 300
# Duration the task is live
assignment_lifetime = 900
# After how many questions do we raise the pay by 1 cent?
pay_rate = 3
# Minimum we're willing to pay per trial
pay_min = 0.01
# Maximum we're willing to pay per trial
pay_max = float('inf')

# Production
production = False

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

def compute_reward(num_queries):

    # start at pay_min cents; scale for every pay_rate questions by 1 cent
    # cap at pay_max cents
    return min(((num_queries // pay_rate) + pay_min) * 0.01, pay_max)

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

    reward = compute_reward(len(queries))

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
    return answers, compute_reward(len(queries))

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

def test_sort(sort, num_iterations=1000, max_int=1000, list_size=1000):
    print('Testing sort...')
    for _ in range(num_iterations):
        xs = random.choices(range(max_int),k=list_size)
        if any( x != y for x,y in zip(sort(xs), sorted(xs)) ):
            print('Sort failed on list {}'.format(xs))
            break
    else:
        print('Ran {} tests successfully'.format(num_iterations))

def test_costs(sort, filename='costs.csv', num_iterations=5, max_int=1000, sizes=range(0,1000001,10000)):
    print('Testing costs...')
    with open(filename, 'w') as f:
        writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Number of elements', 'Average cost', *['Trial {}'.format(x) for x in range(num_iterations)]])
        for size in sizes:
            costs = [None for _ in range(num_iterations)]
            for i in range(num_iterations):
                _, cost = sort(random.choices(range(max_int),k=size))
                costs[i] = cost
            writer.writerow([size, sum(costs)/len(costs), *costs])
    print('Done.')

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
    # test_sort(lambda xs: turksort(xs, compare_greater = computer_compare_greater))
    session = boto3.Session()
    if production:
        print('!!! Running in production !!!')
        print('Cancel now if this was mistaken')
        time.sleep(10)
    test_costs(lambda xs: turksort(xs, compare_greater = computer_compare_greater))
    # client = session.client(
    #     service_name='mturk',
    #     endpoint_url=endpoint_url
    # )
    # test_weight()
