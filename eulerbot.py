from client_handler import ClientHandler
import ujson as json
from bs4 import BeautifulSoup
import requests as re
import os
import random

in_dev = 0
BASE_URL = 'https://projecteuler.net/problem='
PROD_CHANNEL = 'projecteuler'
DEV_CHANNEL = 'bottest'
if in_dev:
    channel = DEV_CHANNEL
else:
    channel = PROD_CHANNEL


class EulerBot(object):
    def __init__(self):
        self.COMMAND_HANDLER = {
            'euler me': self.next_unsolved_problem,
            'previous problem': self.prev_problem,
            'skip problem': self.skip_problem,
            'check answer': self.check_answer,
            'mark as solved problem': self.mark_solved_command,
            'unsolve problem': self.mark_unsolved,
            'go to problem': self.go_to_problem,
            'show solved': self.show_solved,
            'random between': self.random_unsolved_problem
        }

        self.CHANNEL = channel
        self.NAME = 'eulerbot'

        self.PROGRESS_FILE = os.path.join(
            os.getcwd(), 'eulerbot', 'progress.json')
        with open(self.PROGRESS_FILE, 'r') as f:
            self.progress = json.load(f)

        self.current_problem = self.progress["current_problem"]

        self.ANSWER_FILE = os.path.join(
            os.getcwd(), 'eulerbot', 'solution.txt')
        self.answers = self._get_answers()

    def _get_answers(self):
        """Handling the loading of answers from file"""
        answers = {}
        with open(self.ANSWER_FILE, 'r') as f:
            i = 1
            for line in f:
                if i > 4:  # skip first 4 lines
                    (key, val) = (line[:line.find(".")],
                                  line[line.find(".")+1:])
                    answers[key.strip()] = val.strip()
                i += 1
        return answers

    def update_current_problem(self, new_problem):
        self.current_problem = new_problem
        self.progress["current_problem"] = new_problem
        with open(self.PROGRESS_FILE, 'w') as f:
            json.dump(self.progress, f)

    def show_problem(self, problem):
        """Display the statement of the specified problem number"""
        try:
            url = BASE_URL + problem
            r = re.get(url)
            soup = BeautifulSoup(r.text)
            problem_content = soup.find('div', {'class': 'problem_content'})
            message = "Project Euler problem #" + \
                problem + " " + \
                problem_content.text + " \n From url: " + url
            self.update_current_problem(problem)
            return message
        except Exception as e:
            return "There is some error trying to show problem: "+str(problem)\
                + str("\n Error message: ")+str(e)

    def random_unsolved_problem(self, user, channel, message):
        """Go to a random unsolved problem. Update current problem #"""
        range_msg = message[len("eulerbot random between "):]
        beginning, end = self._handle_random_between(range_msg)
        if beginning >= end:
            message = """<end> must be greater than <beginning> for random
            between <beginning> and <end>"""
            return [(channel, message)]
        else:
            random_problem = random.randint(beginning, end)
            while str(random_problem) in self.progress["solved"]:
                random_problem += 1
            message = self.show_problem(str(random_problem))
            return[(channel, message)]

    def _handle_random_between(self, message):
        """Parse message for random unsolved problem that contains between"""
        beginning = int(message[:message.find("and ")])
        if beginning > 0:
            end = int(message[message.find("and ")+3:])
        elif int(message[:message.find("& ")]) > 0:
            beginning = int(message[:message.find("& ")])
            end = int(message[message.find("& ")+1:])
        else:
            beginning = self.current_problem
            end = 628
        return beginning, end

    def next_unsolved_problem(self, user, channel, message):
        """Go to the next unsolved problem. Update current problem #"""
        solved = self.progress["solved"]
        print(solved)
        current_problem = 1
        while str(current_problem) in solved:
            current_problem += 1
        message = self.show_problem(str(current_problem))
        return [(channel, message)]

    def go_to_problem(self, user, channel, message):
        """Go to the specified problem"""
        problem = message[len("eulerbot go to problem "):]
        message = self.show_problem(problem)
        return [(channel, message)]

    def skip_problem(self, user, channel, message):
        """Display the next problem. Update current problem #"""
        new_problem = str(int(self.current_problem) + 1)
        message = self.show_problem(new_problem)

        return [(channel, message)]

    def prev_problem(self, user, channel, message):
        """Display previous problem. Update current problem #"""
        new_problem = str(int(self.current_problem) - 1)
        message = self.show_problem(new_problem)

        return [(channel, message)]

    def check_answer(self, user, channel, message):
        """Check answer and mark as solved if correct"""
        ans = message[len("eulerbot check answer "):]
        problem = self.progress["current_problem"]

        if self.answers[problem] == ans:
            message = "Congrats, " + user + ", you solved " +\
                      "problem #" + str(problem)
            self.mark_solved(problem)
        else:
            message = "Nah, try again!"
        return [(channel, message)]

    def mark_solved(self, problem):
        """Mark problem as solved"""
        self.progress["solved"].append(problem)
        with open(self.PROGRESS_FILE, 'w') as f:
            json.dump(self.progress, f)

    def mark_solved_command(self, user, channel, message):
        """"Mark the problem specified in the message as solved"""
        problem = message[len("eulerbot mark as solved problem "):]
        self.mark_solved(problem)
        message = "Marked problem #" + str(problem) + \
                  " as solved. Solved problems are: " + \
                  str(self.progress["solved"])
        return [(channel, message)]

    def mark_unsolved(self, user, channel, message):
        """Mark a specified problem as unsolved"""
        problem = message[len("eulerbot unsolve problem "):]
        # extract the question number

        try:
            self.progress["solved"].remove(problem)
        except ValueError:
            message = "Problem #"+str(problem)+" not yet solved. " +\
                "Solved problems are: " + \
                str(self.progress["solved"])
            return[(channel, message)]

        with open(self.PROGRESS_FILE, 'w') as f:
            json.dump(self.progress, f)
        message = "Marked problem #" + str(problem) + \
                  " as unsolved. Solved problems are: " + \
                  str(self.progress["solved"])
        return [(channel, message)]

    def show_solved(self, user, channel, message):
        return [(channel, str(self.progress["solved"]))]

    def handle_message(self, user, channel, message):
        """This is the main function that handles
        incoming messages"""
        if channel == self.CHANNEL:
            command = self.get_command(message)
            if command in self.COMMAND_HANDLER:
                return self.COMMAND_HANDLER[command](user, channel, message)
        return []

    def get_command(self, message):
        """Extract command from message"""
        lname = len(self.NAME)
        if message[:lname] == self.NAME:
            for command in self.COMMAND_HANDLER:
                if message[lname:].strip()[:len(command)] == command:
                    return command
        return None


token = 'xoxb-2529601863-416504530626-w6cguCE7sRPZPtMAKvHplgeC'
ch = ClientHandler(token, EulerBot(), channel, log_text=False)
ch.run()
