#Add To Server Link: https://discordapp.com/oauth2/authorize?client_id=463281899020877836&scope=bot

#To do:
#Automatically add players who have their steam accounts linked. EDIT: this may not be possible using the api
#//removeplayerFull @name     - removes all data about that person and all roles from that person
#//tradeBuy
#//tradeSell
#//tradeRefresh
#//Add a save function to trading data

import discord, steam, asyncio, time, os
import urllib.request, urllib.parse, re
from discord.ext.commands import Bot
from discord.ext import commands
from rls.rocket import RocketLeague

#SETTINGS-----------------------------------------------------------------------
#Bot settings
botID            = ""    #Bot token
symb             = "//"   #The symbol used to define the start of a command
roleSymb         = "~"    #The symbol used to define a role used by this bot
specificChannels = True   #False if commands can be used in any text channel
updateRate       = 20     #Minutes between saving data and updating roles
daysOnMarket     = 30     #How many days each item will be held in the trading data without a refresh

#Rocket League Settings
rocketSeason     = "8"    #Current RL season
rocketGameModes  = ["1v1 Solo", "2v2 Duo", "3v3 Solo Standard", "3v3 Standard"] #Current RL ranked game modes, in the same order they appear in the rls.rocket json
rocketTiers      = ["Unranked",                                                 #Current RL ranked tiers, in the same order they appear in the rls.rocket json
                    "Bronze I", "Bronze II", "Bronze III",
                    "Silver I", "Silver II", "Silver III",
                    "Gold I", "Gold II", "Gold III",
                    "Platinum I", "Platinum II", "Platinum III",
                    "Diamond I", "Diamond II", "Diamond III",
                    "Champion I", "Champion II", "Champion III",
                    "Grand Champion"]
rocketTierRoleColours = [["U", discord.Colour(int("818181", 16))], #If the tier startswith x[0] then it's color is x[1]
                        ["B",  discord.Colour.dark_orange()],
                        ["S",  discord.Colour(int("c0c0c0", 16))],
                        ["Go", discord.Colour.gold()],
                        ["P",  discord.Colour.blue()],
                        ["D",  discord.Colour.dark_blue()],
                        ["C",  discord.Colour.purple()],
                        ["Gr", discord.Colour.dark_purple()]]
specialRoles     = [["RL Helper Engineer", "RL Helper Admin", "RL Helper Mod", "RL Helper Member"], #The prilaged roles in order higest to lowest, privlege score for these roles will be increment from 1 startinf left to right, anyone without these has zero
                    [discord.Colour.dark_purple(), discord.Colour.purple(), discord.Colour.purple(), discord.Colour.default()]] #And the colors of the above roles

#GLOBAL VARIABLES---------------------------------------------------------------
client = discord.Client()
players = {}
tradeData = {} #ServerID+"-"+UserID: [["Items Selling"], ["Items Buying"]]
updateRateTemp = updateRate

#GLOBAL FUNCTIONS------------------------------------------------------------------
def dictAppend(dic, key, val):
    if(key in dic):
        dic[key].append(val)
    else:
        dic[key] = [val]
    return dic

def forceLen(string, length):
    while len(string) < length:
        string += " "
    return string
      
def checkSteamID64(id):
    foundID = 0
    if(str(steam.SteamID(id)) == id): #Check if id matches a found one
        foundID = id
    else:
        foundID = steam.steamid.steam64_from_url("http://steamcommunity.com/id/"+id) #Check if id matches a custom url

    if(foundID and str(steam.SteamID(foundID).type)=="EType.Individual"): #If found check if that is the id for an individual
        return foundID
    return 0

def checkRocketID(platform1, id1, returnFull=False):
    if(not platform1): return False
    
    if(platform1=="1" and str(steam.SteamID(id1)) != id1): #Check if id was inputted as custom url
        testID = steam.steamid.steam64_from_url("http://steamcommunity.com/id/"+id1)
        if(testID): id1 = testID
        else:
            testID = steam.steamid.steam64_from_url(id1)
            if(testID): id1 = testID
    
    #Use the RL api to check if the ID exists
    try:
        rl = RocketLeague(api_key='3PE3QPQJDC6RTQOEI76ALAAW3KO6GI9F')
        response = rl.players.player(id=id1, platform=platform1)
        if returnFull: return response.json()
        else: return id1
    
    except Exception as e: #Check if not found, raise if any other error occours
        if(str(type(e))=="<class 'rls.exceptions.ResourceNotFound'>"):
            return False
        else:
            raise e

def getMentionedUser(mention, server):
    #Remove mention values if any
    if(not mention): return False

    #Remove mention characters to get pure id
    if mention[0]=="<":
        mention = mention[1:]
        if mention.endswith(">"):
            mention = mention[:-1]
    if mention[0]=="@":
        mention = mention[1:]
    if mention[0]=="!":
        mention = mention[1:]

    #Allow a way for people to have spaces
    mention = mention.replace(":", " ")

    #Find if the user exists on the server and return the user or False if none found
    for member in server.members:
        if(mention == str(member.id) or mention == member.name + "#" + str(member.discriminator)):
            return member
    return False

def getTierRoleColor(tier):
    for color in rocketTierRoleColours:
        if(tier.startswith(color[0])):
           return color[1]
    return -1
        
    
def getRoles(user):
    roleNames = []
    for role in user.roles:
        roleNames.append(role.name)
    return roleNames

def getPrivilege(user):
    roles = getRoles(user)
    priv = len(specialRoles[0])

    for p in specialRoles[0]:
        if(roleSymb+p in roles): return priv
        priv -= 1
    return priv #should be 0

def savePlayers(path, typeStr):
    global players
    for key in players:
        #open file
        file = open(os.path.join(path, key + " " + typeStr +".txt"),"w")
        first = True
        
        #Add new line between rows
        for row in players[key]:
            if(first):
                first = False
            else:
                file.write('\n')
            
            file.write(' '.join(row))

        #close file
        file.close()

def loadPlayers(path, typeStr):
    dat = {}
    for filename in os.listdir(path): #walk through all files
        keyVal, typeStr1 = filename.split(" ")
        
        if(typeStr1 == typeStr+".txt"): #Check for correct files
            #Get lines from file
            file = open(os.path.join(path, filename), "r")
            file = file.read().split("\n")

            #Add arrays to dict
            for line in file:
                dat = dictAppend(dat, keyVal, line.split(" "))
    return dat    

def getRlRanks(json):
    ranks = []
    for gameMode in range(len(rocketGameModes)):
        gm = "1"+str(gameMode)
        if(rocketSeason in json["rankedSeasons"] and gm in json["rankedSeasons"][rocketSeason]):
            box = [[],[],[],[]]
            box[0] = rocketTiers[json["rankedSeasons"][rocketSeason][gm]["tier"]]
            box[1] = str(int(json["rankedSeasons"][rocketSeason][gm]["division"])+1)
            box[2] = json["rankedSeasons"][rocketSeason][gm]["rankPoints"]
            box[3] = json["rankedSeasons"][rocketSeason][gm]["matchesPlayed"]
            ranks.append(box)
        else:
            ranks.append([rocketTiers[0], "NA", "NA", 0])
    return ranks

def getRlTiers(json): 
    tiers = []
    for gameMode in range(len(rocketGameModes)):
        gm = "1"+str(gameMode)
        if(rocketSeason in json["rankedSeasons"] and gm in json["rankedSeasons"][rocketSeason]):
            tiers.append(int(json["rankedSeasons"][rocketSeason][gm]["tier"]))
        else:
            tiers.append(0)
    return tiers

#FUNCTIONS WITH BOT COMMANDS----------------------------------------------------
async def bot_pong(message):
        await client.send_message(message.channel, "**Pong**") #Send pong

async def bot_saveall(message): #message=False when not called by user
    #Check permissions
    if(message and getPrivilege(message.author) < 2):
        await client.send_message(message.channel, "You do not have permission to use that command.")
        return

    #Save individual data
    savePlayers("saved data", "People")

    #Finish
    if(message): await client.send_message(message.channel, "All bot data backed up successfully.")

async def bot_loadall(message): #message=False when not called by user
    #Check permissions
    if(message and getPrivilege(message.author) < 2):
        await client.send_message(message.channel, "You do not have permission to use that command.")
        return

    #Load individual data
    global players
    players = loadPlayers("saved data", "People")

    #Finish
    if(message): await client.send_message(message.channel, "All bot data loaded successfully.")

async def bot_clearRoles(message):
    #Check permissions
    if(getPrivilege(message.author) < 3):
        await client.send_message(message.channel, "You do not have permission to use that command.")
        return

    #Clear all roles, it had to be looped as message.server.roles never gave the whole list, just some
    await client.send_message(message.channel, "Clearing bot roles...")
    while(True):
        found = False
        for role in message.server.roles:
            if(role.name.startswith(roleSymb)):
                try:
                    await client.delete_role(message.server, role)
                    found = True
                except Exception as e:
                    eType = str(type(e))
                    if(eType=="<class 'discord.errors.Forbidden'>" or eType=="<class 'discord.errors.NotFound>"):
                        await client.send_message(message.channel, "    -Error: The bot does not have permissions to manage server roles. It is also possible that the bots roll is below the one's it needs to maintain.")
                        return
                    else:
                        raise e
        if(not found): break

    #Finish
    await client.send_message(message.channel, "All bot roles have be cleared successfully.")

async def bot_createRoles(message, dat):
    #Check permissions
    if(getPrivilege(message.author) < 3):
        await client.send_message(message.channel, "You do not have permission to use that command.")
        return

    #Get args
    mode = ""
    if(len(dat)>1 and dat[1].lower == "hard"): mode = "hard"
    
    #Get role names
    rolesToAdd = []
    colorToAdd = []

    for r in range(len(specialRoles[0])): #Get special roles
           rolesToAdd.append(roleSymb+specialRoles[0][r])
           colorToAdd.append(specialRoles[1][r])
           
    for gm in rocketGameModes: #Get rank roles
        for tier in rocketTiers:
            rolesToAdd.append(roleSymb+gm+" - "+tier) #[name, color]
            colorToAdd.append(getTierRoleColor(tier))
    
    #Remove unwanted roles
    await client.send_message(message.channel, "1/2   Removing old roles...")
    while(True):
        found = False
        for role in message.server.roles:
            name = role.name
            if(name.startswith(roleSymb) and name not in rolesToAdd):
                try:
                    await client.delete_role(message.server, role)
                    found = True
                except Exception as e:
                    eType = str(type(e))
                    if(eType=="<class 'discord.errors.Forbidden'>" or eType=="<class 'discord.errors.NotFound>"):
                        print(message.server.name, role.name)
                        await client.send_message(message.channel, "    -Error: The bot does not have permissions to manage server roles. It is also possible that the bots roll is below the one's it needs to maintain.")
                        return
                    else:
                        raise e
        if(not found): break

    #Add new roles if they don't exist
    await client.send_message(message.channel, "2/2   Creating new roles...")
    for i in range(len(rolesToAdd)):
        if(discord.utils.get(message.server.roles, name=rolesToAdd[i]) == None): #If role doesn't exist in server --roleData[0] not in servroleNames):
            try:
                await client.create_role(message.server, name=rolesToAdd[i], colour=colorToAdd[i])
            except Exception as e:
                if(str(type(e))=="<class 'discord.errors.Forbidden'>"):
                    await client.send_message(message.channel, "    -Error: The bot does not have permissions to manage server roles. It is also possible that the bots roll is below the one's it needs to maintain.")
                    return
                else:
                    raise e

    #Finish
    await client.send_message(message.channel, "Required roles refreshed successfully.")

async def bot_addPerson(message, dat):
    #Check permissions
    '''
    if(getPrivilege(message.author) < 2):
        await client.send_message(message.channel, "You do not have permission to use that command.")
        return
    '''
        
    #Check for correct length
    helpMsg  = "Help: " + dat[0].lower()+" @user platform RocketLeagueID"
    if(len(dat)!=4): #Check that it's the right length
        await client.send_message(message.channel, helpMsg)
        return

    #Set variables for input checks
    user     = getMentionedUser(dat[1], message.server)
    platform = dat[2].lower()
    rocketID = dat[3]
        
    if(platform == "steam"):   platform = "1"
    if(platform == "ps4"):     platform = "2"
    if(platform == "xboxone"): platform = "3"

    #Check for correct inputs
    error = ""
    
    if(platform!="1" and platform!="2" and platform!="3"): #Check platform is correct
        error += "\n    -Error: Platform must be Steam, PS4, XboxOne or 1, 2, 3."
        platform=False

    if(not user): #Check if user exists
        error += "\n    -Error: Discord user not found in server. Make sure to type user as a mention or full username eg: username#1234."

    rocketID = checkRocketID(platform, rocketID) #Check if RLID exists
    if(not rocketID):
        error += "\n    -Error: Rocket-League_ID not found for that platform."

    if error:
        await client.send_message(message.channel, helpMsg+error)
        return

    #Get variables for the rest of the process
    userData = [str(user.id), str(rocketID), platform]
    serverID = str(message.server.id)
        
    #Save the new player data
    if(serverID in players and userData in players[serverID]):
        await client.send_message(message.channel, "User data already exists.")
    else:
        dictAppend(players, serverID, userData)
        await client.send_message(message.channel, "New user data added successfully.")

    #UpdateAndSave
    await bot_saveall("")

    if message.server.id in players:
        await bot_updateRoles("", message.server, ["Auto", str(user.id)])

async def bot_removePerson(message, dat):
    #Check permissions
    if(getPrivilege(message.author) < 2):
        await client.send_message(message.channel, "You do not have permission to use that command.")
        return
        
    #Check for correct length
    helpMsg  = "Help: " + dat[0].lower()+" @user platform RocketLeagueID"
    if(len(dat)!=4): #Check that it's the right length
        await client.send_message(message.channel, helpMsg)
        return

    #Set variables for input checks
    user     = getMentionedUser(dat[1], message.server)
    platform = dat[2].lower()
    rocketID = dat[3]
        
    if(platform == "steam"):   platform = "1"
    if(platform == "ps4"):     platform = "2"
    if(platform == "xboxone"): platform = "3"

    #Check for correct inputs
    error = ""
    
    if(platform!="1" and platform!="2" and platform!="3"): #Check platform is correct
        error += "\n    -Error: Platform must be Steam, PS4, XboxOne or 1, 2, 3."
        platform=False

    if(not user): #Check if user exists
        error += "\n    -Error: Discord user not found in server. Make sure to type user as a mention or full username eg: username#1234."

    rocketID = checkRocketID(platform, rocketID) #Check if RLID exists
    if(not rocketID):
        error += "\n    -Error: Rocket-League_ID not found for that platform."

    if error:
        await client.send_message(message.channel, helpMsg+error)
        return

    #Get variables for the rest of the process
    userData = [str(user.id), str(rocketID), platform]
    serverID = str(message.server.id)
        
    #Save the new player data
    if(serverID in players and userData in players[serverID]):
        players[serverID].remove(userData)
        await client.send_message(message.channel, "User data removed successfully.")
    else:
        await client.send_message(message.channel, "User data does not exist.")

async def bot_getInfo(message, dat):
    #Check if right length
    helpMsg  = "Help: " + dat[0].lower()+" @user"
    if(len(dat)!=2): #Check that it's the right length
        await client.send_message(message.channel, helpMsg)
        return

    #Set variables for input checks
    user = getMentionedUser(dat[1], message.server)
    if(not user): #Check if user exists
        await client.send_message(message.channel, helpMsg+"\n    -Error: Discord user not found in server. Make sure to type user as a mention or full username eg: username#1234.")
        return

    #Check if server exists in data
    if(message.server.id not in players):
        await client.send_message(message.channel, "The users data is not recorded on this server. Use **"+symb+"addplayer @user platform RocketLeagueID** to add the users data.")
        return

    #Get basic user data
    playerDat = []
    for data in players[message.server.id]:
        if(data[0]==str(user.id)):
            playerDat.append(checkRocketID(data[2], data[1], True))

    #Check if empty
    found = False
    for data in playerDat:
        if(data): found = True
        break

    if(not found):
        await client.send_message(message.channel, "The users data is not recorded on this server. Use **"+symb+"addplayer @user platform RocketLeagueID** to add the users data.")
        return

    #Get user data to display
    outputs = []
    for data in playerDat:
        #Get player data
        output1 = []
        output1.append(["Display Name:",     data['displayName']])
        output1.append(["Platform:",         data['platform']['name']])
        output1.append(["Rocket League ID:", data['uniqueId']])

        #Get rank data
        ranks = getRlRanks(data)
        output2 = []
        for gameMode in range(len(rocketGameModes)):
            if(ranks[gameMode] == [rocketTiers[0], "NA", "NA", 0]):
                output2.append([["Not Played", ""]])
            else:
                box = []
                box.append(["Tier:", ranks[gameMode][0]])
                box.append(["Division:", ranks[gameMode][1]])
                box.append(["Rank Points:", ranks[gameMode][2]])
                box.append(["Matches Played:", ranks[gameMode][3]])
                output2.append(box)

        #Get stat data
        output3 = []
        output3.append(["Wins:",             data["stats"]["wins"]])
        output3.append(["Goals:",            data["stats"]["goals"]])
        output3.append(["MVPs:",             data["stats"]["mvps"]])
        output3.append(["Saves:",            data["stats"]["saves"]])
        output3.append(["Shots:",            data["stats"]["shots"]])
        output3.append(["Assists:",          data["stats"]["assists"]])
        outputs.append([output1, output2, output3])

    #Create and send message
    msg = "```"
    first = True
    for o in outputs:
        #Add new line for each new account linked
        if(first):
            first = False
        else:
            msg += "\n\n"

        #Basic data
        for line in o[0]: msg += forceLen(str(line[0]), 18)+str(line[1])+"\n"

        #Ranked data
        for gameMode in range(len(rocketGameModes)):
            msg += "\nRanked "+rocketGameModes[gameMode]+":\n"
            for line in o[1][gameMode]: msg += "  "+forceLen(str(line[0]), 16)+str(line[1])+"\n"

        #Stat data
        msg += "\nStats:\n"
        for line in o[2]: msg += "  "+forceLen(str(line[0]), 9)+str(line[1])+"\n"
        msg += "____________________"
        
    msg += "```"
    await client.send_message(message.channel, msg)

async def bot_updateRoles(message, server, dat=["", "a"]): #Message will be False when called automatically
    global players
    helpMsg  = "Help: " + dat[0].lower()+" @user"
    
    if(message and len(dat)!=2): #Check that it's the right length
        await client.send_message(message.channel, helpMsg)
        return    

    #Decide on function mode
    res = ""
    if(dat[1] in ["all", "a"]):
        #Check if server data exists
        if(message and (server.id not in players)): 
            await client.send_message(message.channel, helpMsg+"\n    -Error: No user data is not recorded on this server. Use **"+symb+"addplayer @user platform RocketLeagueID** to add the users data.")
            return
        
        #Run main function for all players
        if(message): await client.send_message(message.channel, "Roles being updated...")
        for p in players[server.id]:
            dat[1] = p[0]
            res = bot_updatePlayerRoles(server, dat)

            #Remove and add roles if no errors in main function
            if(res[0]):
                try:
                    user = getMentionedUser(dat[1], server)
                    await client.remove_roles(user, *res[1])
                    await client.add_roles(user, *res[2])
                except Exception as e:
                    if(str(type(e))=="<class 'discord.errors.Forbidden'>"):
                        res = [False, "\n    -Error: The bot does not have permissions to manage server roles. It is also possible that the bots roll is below the one's it needs to maintain."]
                        break
                    else:
                        raise e
    else:
        #Check if server data exists
        if(message and server.id not in players): 
            await client.send_message(message.channel, helpMsg+"\n    -Error: The users data is not recorded on this server. Use **"+symb+"addplayer @user platform RocketLeagueID** to add the users data.")
            return

        #Run main function for single player
        if(message): await client.send_message(message.channel, "Roles being updated...")
        res = bot_updatePlayerRoles(server, dat)

        #Remove and add roles if no errors in main function
        if(res[0]):
            try:
                user = getMentionedUser(dat[1], server)
                await client.remove_roles(user, *res[1])
                await client.add_roles(user, *res[2])
            except Exception as e:
                if(str(type(e))=="<class 'discord.errors.Forbidden'>"):
                    res = [False, "\n    -Error: The bot does not have permissions to manage server roles. It is also possible that the bots roll is below the one's it needs to maintain."]
                else:
                    raise e

    #Check for error
    if(message and not res[0]):
        await client.send_message(message.channel, helpMsg+res[1])
        return

    #Finish
    if(message): await client.send_message(message.channel, "Roles updated successfully.")

def bot_updatePlayerRoles(server, dat):
    global players
    
    #Set variables for input checks
    user = getMentionedUser(dat[1],  server)
    if(not user): #Check if user exists
        return [False, "\n    -Error: Discord user not found in server. Make sure to type user as a mention or full username eg: username#1234 or type all for all players."]
    
    #Get basic user data
    playerDat = []
    for data in players[str(server.id)]:
        if(data[0]==str(user.id)):
            playerDat.append(checkRocketID(data[2], data[1], True))

    #Check if empty
    found = False
    for data in playerDat:
        if(data): found = True
        break

    if(not found):
        return [False, "\n    -Error: The users data is not recorded on this server. Use **"+symb+"addplayer @user platform RocketLeagueID** to add the users data."]

    #Get ranks
    highestTiers = getRlTiers(playerDat[0])
    for data in range(1, len(playerDat)):
         gmTiers = getRlTiers(playerDat[data])
         for tier in range(len(gmTiers)):
             if(gmTiers[tier] > highestTiers[tier]):
                 highestTiers[tier] = gmTiers[tier]
                 
    #Get roles to remove
    rolesToRem = []
    for role in user.roles:
        if(role.name.startswith(roleSymb) and role.name[len(roleSymb):] not in specialRoles[0]):
            rolesToRem.append(role)

    #Get roles to add
    rolesToAdd = []
    for gameMode in range(len(rocketGameModes)):
        rolesToAdd.append(discord.utils.get(server.roles, name=roleSymb+rocketGameModes[gameMode]+" - "+rocketTiers[highestTiers[gameMode]]))

    return [True, rolesToRem, rolesToAdd]

async def bot_nextUpdateCheck(message):
    time = str(updateRate-updateRateTemp)
    if(time=="1"):
        await client.send_message(message.channel, "Bot data will be updated in "+time+" minute.")
    else:
        await client.send_message(message.channel, "Bot data will be updated in "+time+" minutes.")


    
#BOT THREADS--------------------------------------------------------------------
async def clock(): #Call this with "asyncio.async(clock(1))"
    global updateRate, updateRateTemp, players

    while True:
        #Count down minutes
        if(updateRateTemp % updateRate):
            #Increment timer
            updateRateTemp += 1
        else:
            #Save data
            await bot_saveall("")

            #Update roles for all servers
            for server in client.servers:
                if server.id in players:
                    await bot_updateRoles("", server)

            #Reset timer
            updateRateTemp = 1

        #Sleep for the required seconds 
        await asyncio.sleep(60)

#BOT EVENTS---------------------------------------------------------------------
@client.event
async def on_ready(): #CODE HERE RUNS WHEN BOT TURNS ON
    print("Logged in as")
    print(client.user.name)
    print(client.user.id)
    
    await bot_loadall("")
    client.loop.create_task(clock())
    print("------")

@client.event
async def on_message(message): #CODE HERE WHEN A PERSON SENDS A MESSAGE
    dat = message.content #Get message as string

    #Check if command
    if(dat.startswith(symb)):
        dat = re.sub(' +',' ',dat) #Remove multiple spaces
        dat = dat.split(" ")       #Split at spaces
        comm = dat[0][len(symb):].lower()
    else:
        return

    channelName = message.channel.name
    if(channelName.startswith("rlh")):
        if("comm" in channelName or not specificChannels):
            #Pong command
            if comm == "ping": #If the first word of the message was the ping command
                await bot_pong(message)
                return
            #Save all data Command
            if comm == "saveall":
                await bot_saveall(message)
                return
            #Load all command
            if comm == "loadall":
                await bot_loadall(message)
                return
            #Create roles command
            if comm == "createroles":
                await bot_createRoles(message, dat)
                return
            if comm in ["removeroles", "clearroles"]:
                await bot_clearRoles(message)
                return  
            #Add person command
            if comm == "addplayer":
                await bot_addPerson(message, dat)
                return
            #Remove person command
            if comm in ["removeplayer", "remplayer"]:
                await bot_removePerson(message, dat)
                return
            #Get info command
            if comm in ["about", "info", "getinfo", "showinfo", "player", "playerinfo", "showplayerinfo"]:
                await bot_getInfo(message, dat)
                return
            #Update player roles
            if comm in ["updateroles", "fixroles", "uproles"]:
                await bot_updateRoles(message, message.server, dat)
                return
            #Check for server update
            if comm in ["nextupdate", "nextserverupdate", "nextbotupdate", "nextrlhupdate"]:
                await bot_nextUpdateCheck(message)
                return
        if("trade" in channelName or "trading" in channelName or not specificChannels):
            pass
            
#RUN----------------------------------------------------------------------------
#Initiate bot
client.run(botID)
