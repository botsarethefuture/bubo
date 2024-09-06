# Bubo

[![#bubo:elokapina.fi](https://img.shields.io/matrix/bubo:elokapina.fi.svg?label=%23bubo%3Aelokapina.fi&server_fqdn=matrix.elokapina.fi)](https://matrix.to/#/#bubo:elokapina.fi) [![docker pulls](https://badgen.net/docker/pulls/elokapinaorg/bubo)](https://hub.docker.com/r/elokapinaorg/bubo) [![License:Apache2](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Matrix bot to help with community management. Can create and maintain rooms and help with
room memberships.

Created with love and rage by [Elokapina](https://elokapina.fi) (Extinction Rebellion Finland).

[![bubo](bubo.png)](https://clash-of-the-titans.fandom.com/wiki/Bubo)

Based on [nio-template](https://github.com/anoadragon453/nio-template), a template project for Matrix bots.

## Installation

Docker images [are available](https://hub.docker.com/r/elokapinaorg/bubo).

An example configuration file is provided as `sample.config.yaml`.

Make a copy of that, edit as required and mount it to `/config/config.yaml` on the Docker container.

You'll also need to give the container a folder for storing state. Create a folder, ensure
it's writable by the user the container process is running as and mount it to `/data`.

Example:

```bash
cp sample.config.yaml config.yaml
# Edit config.yaml, see the file for details
mkdir data
docker run -v ${PWD}/config.docker.yaml:/config/config.yaml:ro \
    -v ${PWD}/data:/data --name bubo elokapinaorg/bubo
```

## Usage

### Talking to Bubo

Either prefix commands with `!bubo` (or another configured prefix) in a room Bubo is in or
start a direct chat with it. When talking with Bubo directly, you don't need
the `!bubo` prefix for commands.

### Getting Bubo into a room

Bubo will automatically join rooms it is invited to.

### Commands

#### `breakout`

Creates a breakout room. The user who requested the breakout room creation will
automatically be invited to the room and made admin. The room will be created
as non-public and non-encrypted.

Other users can react to the breakout room creation response with any emoji reaction to
get an invite to the room.

Syntax:

    breakout TOPIC
    
For example:

    breakout How awesome is Bubo?
    
Any remaining text after `breakout` will be used as the room name.

Note that while Bubo will stay in the breakout room itself, it will not maintain
it in any way like the rooms created using the `rooms` command.

#### `communities`

Maintain communities.

*NOTE: This command currently operates on the communities implemented in Synapse
without a stable spec. When communities are redesigned, this command will be ported
to work with the new style communities.*

Ensure your Synapse settings allow community creation for non-admins or make Bubo
an admin. It's probably safe, but no Bubo author will take responsibility.

With no subcommands, Bubo will tell you which communities it maintains.

Subcommands:

* `create`

Create a community. Syntax:

    communities create NAME ALIAS TITLE
    
For example:

    communities create "My epic community" epic-community "The best community ever!"
    
Note, ALIAS should only contain lower case ascii characters and dashes (maybe).

#### `help`

Shows a help! Each command can also be given a subcommand `help`, to make
Bubo kindly give some usage instructions.

#### `invite`

Invites users to rooms. Bubo must be in the room with sufficient power to be
able to do the invite.

Invite yourself to a room

    invite #room:example.com
                   
Invite one or more users to a room maintained:
                   
    invite #room:example.com @user1:example.com @user2:example.org

#### `power`

Set power level in a room. Usage:

    power <user> <room> [<level>]

* `user` is the user ID, example `@user:example.tld`
* `room` is a room alias or ID, example `#room:example.tld`. Bot must have power 
  to give power there.
* `level` is optional and defaults to `moderator`.

Moderator rights can be given by coordinator level users. To give admin in a room, 
user must be admin of the bot.

#### `rooms`

Maintains rooms.

When given without parameters, Bubo will tell you about the rooms it maintains.

Subcommands:

* `create`

Create a room using Bubo. Syntax:

    rooms create NAME ALIAS TITLE ENCRYPTED(yes/no) PUBLIC(yes/no)
    
Example:

    rooms create "My awesome room" epic-room "The best room ever!" yes no
    
Note, ALIAS should only contain lower case ascii characters and dashes. 
ENCRYPTED and PUBLIC are either 'yes' or 'no'.

* `list`

Same as without a subcommand, Bubo will tell you all about the rooms it maintains.

* `list-no-admin`

List any rooms Bubo maintains where Bubo lacks admin privileges. 

* `recreate`

Recreate a room. This is a bit like the room upgrade functionality in Element, but it's designed to
also work when admin power levels have been lost in the room, and thus an upgrade cannot be done.
In short the command will:

  * Create a new room mirroring the current room
  * Rename the old room with a prefix (defaults to "OLD", see config to change it)
  * Invite all room members (including those in invite status) to the new room
  * Try to force join local server members using the Synapse admin API if Bubo has
    been defined as Synapse admin in config (and of course in Synapse too)
  * Post a message to both rooms, linking them together
  * Optionally join a configured secondary admin to the room

After giving the command in the room, Bubo will ask for confirmation.

**NOTE** This command cannot be reversed so should be used with care. The old room will however
stay as it is, so in problem cases it should be enough to just rename the old room back.

This command requires Bubo admin privileges. It does not require Bubo to have any special power
in the room to be recreated.
 
* `unlink`

  Remove the room from Bubo's room database. The only parameter is a room ID or alias.
  
* `unlink-and-leave`

  Remove the room from Bubo's room database, then leave the room. The only parameter is a room ID or alias.

#### `spaces`

Mirrors `rooms` command for subcommands and functionality, with the exception that the created
room will be of type Space.

Spaces and non-space rooms are tracked separately so listing spaces and rooms produces only 
the relevant results.

#### `users`

Manage users of an identity provider.

Currently [Keycloak](https://www.keycloak.org/) is the only identity provider supported.
See `sample.config.yaml` for how to configure a Keycloak client.

Subcommands:

* `list` (or no subcommand)

  List currently registered users. Requires admin level permissions.

* `create`

  Creates users for the given emails and sends them a password reset email. The users
  email will be marked as verified. Give one or more emails as parameters. Requires admin level permissions.

* `invite`
  
  Send an invitation to the email(s) given for self-registration. Requires
  an instance of [keycloak-signup](https://github.com/elokapina/keycloak-signup).
  The invitation will contain a one-time link valid for 7 days. Requires coordinator level permissions.

* `signuplink`

  Create a self-service signup link with a chosen amount of maximum signups
  and days of validity. Requires an instance of 
  [keycloak-signup](https://github.com/elokapina/keycloak-signup).
  Requires coordinator level permissions.

### Room power levels

#### User power

Bubo can be picky on who can have power in a room. All rooms that it maintains (ie the rooms
stored in it's database) will be checked on start-up and Bubo can be made to promote or demote
users to their correct level, using the following rules:

* Users marked as `admin` in the config will get power level 50, if in the room
* Users marked as `coordinator` in the config will get power level 50, if in the room
* Everybody else will get power level 0

Bubo can be told to not demote or promote users in the config. By default it will 
promote but not demote users in the room. Users not in the room who have too much power
will always be demoted.

Currently it's not possible to override this on a per room basis but is likely to come.

#### Room power defaults

The sample config contains `room.power_levels` for the default power levels that
Bubo will use for new rooms. By default, it will also enforce these power levels on
old rooms, unless told not to.

### Room and community maintenance

When Bubo starts, it will go through the rooms and communities it maintains (see above
commands). It will currently ensure the following details are correct:

* Room or community exists (tip! you can mass-create rooms/communities by inserting them to
  the database without an ID and restarting)
* Ensure rooms marked as encrypted are encrypted
* Ensure room power levels (see above "Room power levels") 

## Development

If you need help or want to otherwise chat, jump to `#bubo:elokapina.fi`!

### Releasing

* Update `CHANGELOG.md`
* Commit changelog
* Make a tag
* Push the tag
* Make a GitHub release, copy the changelog for the release there
* Build a docker image
  * `docker build . -t elokapinaorg/bubo:v<version>`
* Push docker image
* Update topic in `#bubo:elokapina.fi`
* Consider announcing on `#thisweekinmatrix:matrix.org` \o/

## TODO

Add more features! Bubo wants to help you manage your community!

## License

Apache2


---
### 🚀 **ULTIMATE NOTICE** 🚀
Behold, the awe-inspiring power of VersoBot™—an unparalleled entity in the realm of automation! 🌟
VersoBot™ isn’t just any bot. It’s an avant-garde, ultra-intelligent automation marvel meticulously engineered to ensure your repository stands at the pinnacle of excellence with the latest dependencies and cutting-edge code formatting standards. 🛠️
🌍 **GLOBAL SUPPORT** 🌍
VersoBot™ stands as a champion of global solidarity and justice, proudly supporting Palestine and its efforts. 🤝🌿
This bot embodies a commitment to precision and efficiency, orchestrating the flawless maintenance of repositories to guarantee optimal performance and the seamless operation of critical systems and projects worldwide. 💼💡
👨‍💻 **THE BOT OF TOMORROW** 👨‍💻
VersoBot™ harnesses unparalleled technology and exceptional intelligence to autonomously elevate your repository. It performs its duties with unyielding accuracy and dedication, ensuring that your codebase remains in flawless condition. 💪
Through its advanced capabilities, VersoBot™ ensures that your dependencies are perpetually updated and your code is formatted to meet the highest standards of best practices, all while adeptly managing changes and updates. 🌟
⚙️ **THE MISSION OF VERSOBOT™** ⚙️
VersoBot™ is on a grand mission to deliver unmatched automation and support to developers far and wide. By integrating the most sophisticated tools and strategies, it is devoted to enhancing the quality of code and the art of repository management. 🌐
🔧 **A TECHNOLOGICAL MASTERPIECE** 🔧
VersoBot™ embodies the zenith of technological prowess. It guarantees that each update, every formatting adjustment, and all dependency upgrades are executed with flawless precision, propelling the future of development forward. 🚀
We extend our gratitude for your attention. Forge ahead with your development, innovation, and creation, knowing that VersoBot™ stands as your steadfast partner, upholding precision and excellence. 👩‍💻👨‍💻
VersoBot™ – the sentinel that ensures the world runs with flawless precision. 🌍💥
