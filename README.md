# Turksort

## About

Turksort is a novel sorting algorithm that uses human intelligence to compare the elements of a (possibily) heterogeneous list.

You can read more about it in the [paper](/paper/turksort.tex/).

## Setup

1. Clone this repository.

```bash
$ git clone https://github.com/cole-k/turksort.git
```

2. Install a recent verion of [Python 3](https://www.python.org/downloads/).
3. Create a Mechanical Turk account and [get it set up](https://www.mturk.com/get-started).
4. Install [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/quickstart.html#installation) and set up your credentials if you didn't already while creating your Mechnical Turk account.
5. Check that the `production` variable is set to `False` in `turksort.py` and the `debug` variable is set to `True`, then run

```bash
$ python3 turksort.py
```

This should sort a sample list. The program will output links to the sandbox that you can follow to provide human input.

## Future plans

[ ] Finish paper writeup
[ ] Create graphs of performance
[ ] Make this into a library and clean up the code
[ ] Parallelization
