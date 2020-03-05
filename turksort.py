import time
import boto3
import random
from xml.dom.minidom import parseString

wait_time = 5

# Format item -- Description
#           n -- Index (0-based)
#           m -- Index (1-based, equal to n + 1)
#        left -- Left side of comparison
#       right -- Right side of comparison
button_group = \
'''
        <div id="div{n}">
          <h3> Question {m} </h3>
          <table>
            <tr>
              <th><pre>     </pre></th>
              <th>Left</th>
              <th><pre>     </pre></th>
              <th>Right</th>
            </tr>
            <tr>
              <td><pre>     </pre></td>
              <td>{left}</td>
              <td><pre>     </pre></td>
              <td>{right}</td>
            </tr>
          </table>

          <crowd-radio-group>
            <crowd-radio-button name="left.{n}">Left</crowd-radio-button>
            <crowd-radio-button name="equal.{n}">Neither</crowd-radio-button>
            <crowd-radio-button name="right.{n}">Right</crowd-radio-button>
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
    answers = [ None for _ in queries ]
    reward = min(((len(queries) // 5) + 1) * 0.01, 0.10)
    with open('form-template.xml', 'r') as f:
        form = f.read()
        contents = ''
        for n, (x,y) in enumerate(queries):
            contents += button_group.format(n=n, m=n+1,left=str(x), right=str(y))
        question = form.format(contents)
    response = client.create_hit(
        MaxAssignments=1,
        LifetimeInSeconds=1800,
        AssignmentDurationInSeconds=300,
        Reward='{:.2f}'.format(reward),
        Title='Which of these two objects is greater?',
        Keywords='quick, easy, question, answer, compare',
        Description='For each pair, pick which of the two is greater.',
        Question=question,
        QualificationRequirements=[],
    )

    hit_id = response['HIT']['HITId']
    print('Waiting on a response',end='',flush=True)
    while True:
        print('.',end='',flush=True)
        time.sleep(wait_time)
        assignments_response = client.list_assignments_for_hit(
            HITId=hit_id,
            AssignmentStatuses=['Submitted', 'Approved']
        )
        if assignments_response['NumResults'] >= 1:
            break
    contents = parseString(assignments_response['Assignments'][0]['Answer'])
    for node in contents.getElementsByTagName('Answer'):
        n, field, isCorrect = getAnswerContents(node)
        if isCorrect:
            answers[n] = field
    print()
    return answers

def computer_compare_greater(queries):
    answers = queries.copy()
    for i,(x, y) in enumerate(queries):
        if x > y:
            answers[i] = 'left'
        elif x < y:
            answers[i] = 'right'
        else:
            answers[i] = 'equal'
    return answers

def turksort(xs, compare_greater = turk_compare_greater):
    '''
    Sorts any array whose elements can be displayed for comparison.

    Simplicity favored over speed and memory usage, as well as the
    number of queries made.
    '''

    if len(xs) <= 1:
        return xs

    pivot, *rest = xs

    queries = [ (pivot, x) for x in rest ]

    answers = compare_greater(queries)

    lesser  = [ x for i, x in enumerate(rest) if answers[i] == 'left' ]
    equal   = [ pivot ] + [ x for i, x in enumerate(rest) if answers[i] == 'equal' ]
    greater = [ x for i, x in enumerate(rest) if answers[i] == 'right' ]

    return turksort(lesser, compare_greater) + equal + turksort(greater, compare_greater)


def test_sort(sort, num_iterations=1000, max_int=1000, list_size=1000):
    print('Testing sort...')
    for _ in range(num_iterations):
        xs = random.sample(range(max_int),list_size)
        if any( x != y for x,y in zip(sort(xs), sorted(xs)) ):
            print('Sort failed on list {}'.format(xs))
            break
    else:
        print('Ran {} tests successfully'.format(num_iterations))

if __name__ == '__main__':
    # test_sort(lambda xs: turksort(xs, compare_greater = computer_compare_greater))
    session = boto3.Session()
    client = session.client(
        service_name='mturk',
        endpoint_url="https://mturk-requester-sandbox.us-east-1.amazonaws.com"
    )
    # print(turksort(['one' for _ in range(100)]))