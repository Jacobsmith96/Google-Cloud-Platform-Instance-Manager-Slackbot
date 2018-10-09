import os
import time
import re
from libcloud.compute.types import Provider
from libcloud.compute.providers import get_driver
from slackclient import SlackClient

#Slackbot globals
tokenFile = open("token.txt", "r") #Modify this line
slack_client = SlackClient(tokenFile.read().strip())
arbiter_id = None
slackChannel="" #Modify this line
RTM_READ_DELAY = 1 # 1 second delay between reading from RTM
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"

#GCE globals
ComputeEngine = get_driver(Provider.GCE)
projectID = '' # Modify this line
driver = ComputeEngine('', '', project=projectID)
runningNodes = []
nodeDict = {}

#Get a list of all the nodes with their metadata
def get_all_instances():
    return driver.list_nodes()

#Get a list of all the node names
def get_node_names(allNodes):
    nodeNames = []
    for node in allNodes:
        nodeNames.append(node.name)
    return nodeNames

#Parse commands
def parse_bot_commands(slack_events):
        """
            Parses a list of events coming from the Slack RTM API to find bot commands.
            If a bot command is found, this function returns a tuple of command and channel.
            If its not found, then this function returns None, None.
        """
        for event in slack_events:
            if event["type"] == "message" and not "subtype" in event:
                user_id, message = parse_direct_mention(event["text"])
                if user_id == arbiter_id:
                    return message, event["channel"]
        return None, None

#Handle a slack command
def handle_command(command, channel):
    """
        Executes bot command if the command is known
    """
    if channel == slackChannel:
	# Default response is help text for the user
	default_response = "Not sure what you mean. Try *{}*.".format("save <list of instances>")

	# Finds and executes the given command, filling in response
	response = None

	if command.startswith("save"):
	    saveList = command.strip("save ")
	    saveList = re.findall(r"[\w']+", saveList)
            toRemove=[]
	    #saveList now holds the corresponding numbers of instances to save
            response = "Saving the following instances: "
            for elem in saveList:
                if int(elem) in nodeDict:
                    num = int(elem)
                    response+="\n"
                    response+=nodeDict[int(elem)]
                    for node in runningNodes:
                        if node.name == nodeDict[int(elem)]:
                            toRemove.append(node)
                else:
                    slack_client.api_call(
                        "chat.postMessage",
                        channel=slackChannel,
                        text="%s is invalid!" % elem
                    )
            for item in toRemove:
                runningNodes.remove(item)
            # Sends the response back to the channel
            slack_client.api_call(
                "chat.postMessage",
                channel=slackChannel,
                text=response or default_response
            )
            stillKilling = "--------------------------------------------------------------\nStill killing: "
            for node in runningNodes:
                stillKilling+="\n"
                stillKilling+=node.name
            slack_client.api_call(
                "chat.postMessage",
                channel=slackChannel,
                text=stillKilling
            )


def parse_direct_mention(message_text):
        """
            Finds a direct mention (a mention that is at the beginning) in message text
            and returns the user ID which was mentioned. If there is no direct mention, returns None
        """
        matches = re.search(MENTION_REGEX, message_text)
        # the first group contains the username, the second group contains the remaining message
        return (matches.group(1), matches.group(2).strip()) if matches else (None, None)

if __name__ == "__main__":
    startTime = time.time()
    if slack_client.rtm_connect(with_team_state=False):
        print("Instance manager connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        arbiter_id = slack_client.api_call("auth.test")["user_id"]

	slack_client.api_call(
	    "chat.postMessage",	
	    channel=slackChannel,
	    text="Preparing to shutdown the following Google Cloud instances in 5 min (use `@The Arbiter save <list of instance numbers>` to save instances)." 
	)
	#Get all running nodes
	for node in get_all_instances():
	    if node.state == "running":
		runningNodes.append(node)
	#Build string list of nodes
	message=""
	for idx, node in enumerate(get_node_names(runningNodes)):
	    nodeDict[idx] = node
	    message+="%s %s\n" % (idx, node)
            
	#Print running instances
	slack_client.api_call(
	    "chat.postMessage",	
	    channel=slackChannel,
	    text=message
	)

        while time.time() - startTime < 300:
            command, channel = parse_bot_commands(slack_client.rtm_read())
            if command:
                handle_command(command, channel)
            time.sleep(RTM_READ_DELAY)
	
	#Handle actual shutdown here
        finalKill="--------------------------------------------------------------\nKilling the following instances: "
        for node in runningNodes:
            finalKill+="\n"
            finalKill+=node.name

	slack_client.api_call(
	    "chat.postMessage",	
	    channel=slackChannel,
	    text=finalKill
	)

        for node in runningNodes:
            pid = os.fork()
            if pid ==0:
                curDriver = ComputeEngine('', '', project=projectID) 
                curDriver.ex_stop_node(node)
                print("Shutdown node: %s", node.name)
                os.exit()
    else:
        print("Connection failed. Exception traceback printed above.")





