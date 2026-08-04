"""
Aurora Engine - Demo / Debug Data Provider

Supplies fake game library data and generated placeholder artwork so the UI can
be exercised for UI/UX redesign work without a physical Xbox 360 console or a
live FTP connection.

Demo mode is enabled by launching ``python main.py --debug`` (which sets the
``AURORA_DEMO_MODE`` environment variable) and is consumed by the FastAPI server
in :mod:`aurora_engine.server`.
"""

import io
import os
import threading
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

DEMO_ENV_VAR = "AURORA_DEMO_MODE"
# Set AURORA_DEMO_NO_NETWORK=1 to force generated placeholders (skip Xbox Unity /
# online cover lookups) — useful for fully offline UI testing.
DEMO_NO_NETWORK_VAR = "AURORA_DEMO_NO_NETWORK"

# In-memory cache of fetched real artwork so each slot only hits the network once.
# Maps (title_id, category, asset_index) -> bytes | None (None = confirmed miss).
_REAL_ART_CACHE: Dict[tuple, Optional[bytes]] = {}
_REAL_ART_LOCK = threading.Lock()

# Fake console library. TitleIDs / MediaIDs are invented but well-formed so the
# whole UI (grids, editors, previews, rename flow) renders realistically.
_DEMO_GAMES: List[Dict] = [
    {"title_name": "Halo 3", "title_id": "4D5307E6", "db_id": "00000101", "media_id": "9BABC1E1",
     "developer": "Bungie", "publisher": "Microsoft Game Studios", "release_date": "2007-09-25"},
    {"title_name": "Gears of War 2", "title_id": "4D530A26", "db_id": "00000102", "media_id": "1B2C3D4E",
     "developer": "Epic Games", "publisher": "Microsoft Game Studios", "release_date": "2008-11-07"},
    {"title_name": "Forza Motorsport 4", "title_id": "4D5309D3", "db_id": "00000103", "media_id": "2C3D4E5F",
     "developer": "Turn 10 Studios", "publisher": "Microsoft Studios", "release_date": "2011-10-11"},
    {"title_name": "Fable II", "title_id": "4D5307D5", "db_id": "00000104", "media_id": "3D4E5F60",
     "developer": "Lionhead Studios", "publisher": "Microsoft Game Studios", "release_date": "2008-10-21"},
    {"title_name": "Call of Duty: Modern Warfare 2", "title_id": "41560817", "db_id": "00000105", "media_id": "4E5F6071",
     "developer": "Infinity Ward", "publisher": "Activision", "release_date": "2009-11-10"},
    {"title_name": "The Elder Scrolls V: Skyrim", "title_id": "425307E6", "db_id": "00000106", "media_id": "5F607182",
     "developer": "Bethesda Game Studios", "publisher": "Bethesda Softworks", "release_date": "2011-11-11"},
    {"title_name": "Red Dead Redemption", "title_id": "545408A7", "db_id": "00000107", "media_id": "60718293",
     "developer": "Rockstar San Diego", "publisher": "Rockstar Games", "release_date": "2010-05-18"},
    {"title_name": "BioShock", "title_id": "545107F2", "db_id": "00000108", "media_id": "718293A4",
     "developer": "2K Boston", "publisher": "2K Games", "release_date": "2007-08-21"},
    {"title_name": "Portal 2", "title_id": "5655086E", "db_id": "00000109", "media_id": "8293A4B5",
     "developer": "Valve", "publisher": "Valve", "release_date": "2011-04-19"},
    {"title_name": "Mass Effect 2", "title_id": "45410830", "db_id": "0000010A", "media_id": "93A4B5C6",
     "developer": "BioWare", "publisher": "Electronic Arts", "release_date": "2010-01-26"},
    {"title_name": "Assassin's Creed II", "title_id": "55530860", "db_id": "0000010B", "media_id": "A4B5C6D7",
     "developer": "Ubisoft Montreal", "publisher": "Ubisoft", "release_date": "2009-11-17"},
    {"title_name": "Left 4 Dead 2", "title_id": "5655084F", "db_id": "0000010C", "media_id": "B5C6D7E8",
     "developer": "Valve", "publisher": "Valve", "release_date": "2009-11-17"},
]

# Palette used to give each fake game a distinct, stable colour.
_PALETTE = [
    (0x2E, 0x86, 0xDE), (0xE7, 0x4C, 0x3C), (0x27, 0xAE, 0x60), (0x8E, 0x44, 0xAD),
    (0xF3, 0x9C, 0x12), (0x16, 0xA0, 0x85), (0xC0, 0x39, 0x2B), (0x29, 0x80, 0xB9),
    (0xD3, 0x54, 0x00), (0x2C, 0x3E, 0x50), (0x7F, 0x8C, 0x8D), (0x9B, 0x59, 0xB6),
]


def is_demo_mode() -> bool:
    """Returns True when the engine is running in fake-data / debug mode."""
    return os.environ.get(DEMO_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


def network_enabled() -> bool:
    """Whether demo mode may fetch real cover art from online sources."""
    return os.environ.get(DEMO_NO_NETWORK_VAR, "").strip().lower() not in {"1", "true", "yes", "on"}


def enable_demo_mode() -> None:
    """Turns demo mode on for the current process."""
    os.environ[DEMO_ENV_VAR] = "1"


def _normalize(title_id: str) -> str:
    return (title_id or "00000000").strip().upper().zfill(8)


DEMO_GAME_SYNOPSES: Dict[str, str] = {
    "5345080E": "Alpha Protocol is an espionage RPG from Obsidian Entertainment starring Michael Thorton, a newly trained field agent for a black-ops initiative called Alpha Protocol. When his own handlers burn him and leave him for dead, Thorton goes rogue, using his training to track down who set him up and why.\n\nThe game's defining feature is a timed dialogue system: instead of picking exact lines, players choose a tone -- aggressive, professional, or suave -- and those choices ripple into how NPCs treat Thorton, which missions open up, and how relationships and alliances shift. Combat mixes cover-based shooting, stealth, and gadgets, with skills that improve based on how the player actually plays.\n\nThorton's investigation carries him through Saudi Arabia, Rome, Taipei, and Moscow as he untangles a conspiracy linking arms dealers, private military contractors, and a hidden war being fought behind the scenes of global politics.",
    "555307D4": "Assassin's Creed follows Altair Ibn-La'Ahad, a member of the secretive Assassin Brotherhood during the Third Crusade. After a failed mission costs him his rank, Altair is sent to assassinate nine targets across the cities of Jerusalem, Damascus, and Acre to earn back his standing.\n\nMovement is built around free-running across rooftops and crowded medieval streets, using height and crowds to stay hidden before striking. Each assassination is preceded by investigation work -- eavesdropping, pickpocketing, and interrogation -- that reveals a target's habits and security before the player chooses how to strike.\n\nFraming the historical story is a modern-day plot: the whole adventure is a genetic memory being relived by Desmond Miles, a bartender with Assassin ancestry, through a machine called the Animus, hinting at a present-day conflict between Assassins and Templars.",
    "5553083B": "Assassin's Creed II moves the series to Renaissance Italy, following young nobleman Ezio Auditore da Firenze after his father and brothers are executed on false charges by a conspiracy of corrupt officials and Templar agents. Ezio trains as an Assassin to hunt down the conspirators one by one.\n\nThe sequel greatly expands on the original's free-running and stealth with a wider toolkit: hidden blades, throwing knives, smoke bombs, and eventually a pistol, along with a home villa that can be renovated and grows into a source of income across the game. Cities like Florence, Venice, and Forli are dense, vertical playgrounds built for climbing and rooftop chases.\n\nThe modern-day framing story continues too, with Desmond Miles relving Ezio's memories through the Animus while uncovering clues left behind about an ancient civilization and a looming global threat.",
    "555308AE": "Assassin's Creed III jumps forward to the American Revolution, introducing Ratonhnhake:ton, known as Connor, the son of a Mohawk mother and a British Templar father. Raised in a village threatened by colonial expansion, Connor takes up the Assassin's creed to protect his people and fight the Templars manipulating both sides of the war.\n\nThe game trades dense Renaissance cities for a mix of colonial settlements and vast frontier wilderness, adding tree-running through forests, hunting, and a naval combat system that lets Connor captain his own ship, the Aquila, in ocean battles. Historical figures like George Washington and Benjamin Franklin appear throughout the story.\n\nThe present-day thread also comes to a head here, as Desmond Miles and his allies race to stop a solar catastrophe using knowledge uncovered from Connor's memories.",
    "5343080B": "Batman: Arkham Asylum traps the Dark Knight inside Gotham's infamous asylum for the criminally insane after delivering the Joker there, only to discover it was exactly what the Joker wanted. With the Joker seizing control of the facility and its inmates, Batman has to fight, sneak, and detect his way through the island to take it back.\n\nThe game established the series' signature Freeflow combat, which rewards chaining attacks and counters against groups of enemies, alongside a predator-style stealth system for picking off armed thugs from the shadows using gadgets like the batclaw, explosive gel, and detective vision to scan rooms and track clues.\n\nAlong the way Batman faces off against a rogues' gallery including Harley Quinn, Bane, Killer Croc, Poison Ivy, and Scarecrow, whose fear-toxin sequences twist the asylum's corridors into surreal, disorienting set pieces.",
    "57520802": "Batman: Arkham City opens up the series into a sprawling open world: a walled-off slum in the heart of Gotham that corrupt warden Quincy Sharp has turned into a lawless prison where inmates run free. Batman infiltrates the city to investigate a plot by Hugo Strange, who claims to know his secret identity.\n\nFreeflow combat and predator-style stealth return with new gadgets and moves, now set across rooftops, streets, and interiors the player can glide and grapple between freely, encouraging a more patrol-like pace than the corridor-based first game.\n\nArkham City is packed with Batman's rogues' gallery, including the Joker, Two-Face, the Penguin, Mr. Freeze, and Catwoman, who is playable in her own side missions, all converging on a story about Strange's true plans for the caged population.",
    "57520828": "Batman: Arkham Origins is a prequel set years before Arkham Asylum, when Batman is still an early, unproven vigilante feared and hunted by Gotham's police. On a snowbound Christmas Eve, crime lord Black Mask puts a bounty on Batman's head, drawing eight of the world's deadliest assassins into the city to collect it.\n\nBuilt on the Freeflow combat and detective systems of its predecessors, Origins adds a crime-scene investigation tool for reconstructing events and a bigger, more open version of Gotham to glide across between confrontations with hunters like Deathstroke, Bane, and Deadshot.\n\nThe story also marks the first meeting between Batman and a young Joker, laying groundwork for the twisted relationship that defines the rest of the series, alongside an origin for Commissioner Gordon's partnership with the Dark Knight.",
    "41560845": "Blur is an arcade combat racer that puts real, licensed cars from manufacturers like Ford, Dodge, and Lamborghini into weaponized street races. Alongside raw driving skill, players collect and fire power-ups -- shock bolts, mines, shunts, and nitro -- to knock rivals off the road while defending against incoming attacks of their own.\n\nRaces take place across real-world city circuits reimagined as combat tracks, with a leveling system that unlocks new cars and power-ups as players climb the single-player campaign's Fan ranking. A strong multiplayer mode was a major focus, supporting large races with the same weaponized chaos as the campaign.\n\nThe result sits between straight arcade racers and kart-style combat games, aiming for the accessibility of power-up racing without abandoning realistic car handling and licensed vehicles.",
    "58410A7A": "Castlevania: Harmony of Despair is a 2D action game built specifically around online and local co-op, gathering up to six players at once to fight through a single sprawling stage stitched together from locations across the series' history. Rather than a linear story campaign, it plays more like a loot-focused arena run through familiar Castlevania territory.\n\nPlayers choose from a roster of classic protagonists, including Soma Cruz, Alucard, Simon Belmont, and Charlotte Aulin, each with distinct weapons and abilities, and gear picked up during runs carries over to make characters stronger on repeat attempts.\n\nThe large, open stage layout is a deliberate departure from the series' usual tight corridors, letting groups split up to explore, fight bosses, and grab treasure simultaneously across the map.",
    "4B4E084D": "Castlevania: Lords of Shadow 2 continues directly from its predecessor, casting the player as Gabriel Belmont, now transformed into the immortal vampire lord Dracula after centuries of suffering. Weakened and hunted by both an ancient enemy and the modern world, Dracula must reclaim his lost powers to survive.\n\nThe game splits its setting between a gothic castle and a disguised present-day city, with combat built around Dracula's Chaos Claws and Void Sword, each suited to different enemy types, plus vampiric abilities like turning into a swarm of rats or a cloud of mist to slip past obstacles.\n\nStealth sections used to avoid powerful pursuing enemies sit alongside the series' traditional action combat, as the story wrestles with Dracula's identity as both monster and reluctant protector of the world that fears him.",
    "58410847": "Castlevania: Symphony of the Night follows Alucard, the dhampir son of Dracula, as he wakes from centuries of sleep to find his father's castle has risen again. Choosing to oppose Dracula rather than side with him, Alucard sets out through the shifting halls to find out how his father returned and put a stop to it.\n\nWhile earlier Castlevania games were linear stage-by-stage action games, Symphony of the Night opened the castle into one huge, interconnected map that players explore non-linearly, gaining new spells, weapons, and forms -- including a bat, wolf, and mist -- that unlock paths back to previously blocked rooms, a structure that became hugely influential on the genre.\n\nA light RPG layer tracks experience, equipment, and stats, and roughly halfway through the game the castle itself flips upside down into an inverted mirror version, doubling the world to explore.",
    "5841140D": "Child of Light tells the story of Aurora, a young girl who falls into a deep sleep and wakes up in the painterly fantasy realm of Lemuria, only to find the sun, moon, and stars have been stolen by the Queen of the Night. Gifted with the ability to fly, Aurora sets out to reclaim them and find her way home.\n\nExploration is handled as a side-scrolling platformer, while combat switches to a turn-based system on a timeline where speed and interrupting enemy actions matter as much as raw power. Aurora is joined along the way by a growing party of companions, including a firefly guide named Igniculus who can slow enemies and heal allies mid-battle.\n\nThe game's dialogue is written entirely in rhyming verse, reinforcing its fairy-tale, storybook tone, and its visuals use a soft watercolor art style that stands apart from most other games on the console.",
    "4E4D083A": "Dark Souls drops the player, an Undead cursed to endlessly reawaken after death, into the crumbling kingdom of Lordran. With only fragments of a prophecy to go on, the player must ring two Bells of Awakening and confront the fading Lords who once held back the encroaching Age of Dark.\n\nCombat is slow and deliberate, built around stamina management, careful positioning, and reading enemy attack patterns rather than button-mashing; death sends the player back to the last bonfire checkpoint and drops their accumulated souls at the death location, recoverable only by surviving one more trip back.\n\nLordran itself is designed as one continuous, tightly looping space rather than separate levels, with shortcuts that fold back on themselves as the map opens up, encouraging players to memorize the world instead of a linear path. Sparse storytelling delivered through item descriptions and environmental detail leaves much of Lordran's history for players to piece together themselves.",
    "465307E4": "Dark Souls II sends a new cursed Undead to the kingdom of Drangleic, drawn by rumors that its ruler holds a cure for the Undead Curse. The journey winds through ruined castles, poisoned swamps, and sunken cities in search of great souls needed to challenge Drangleic's throne.\n\nThe game keeps the series' punishing, stamina-driven combat while loosening the tightly interconnected level design of the original in favor of more standalone areas linked by hub travel, and introduces mechanics like gradually reduced max health from repeated deaths, pushing players toward more careful, deliberate play.\n\nA huge roster of weapons, spells, and covenants supports many different build styles, and returning bonfires once again serve as the game's checkpoints, respite points, and gateway to leveling up through the Emerald Herald.",
    "4541090B": "Dragon Age 2 follows Hawke, a refugee fleeing the destruction of their home who arrives in the city of Kirkwall with next to nothing. Over the following decade, Hawke claws their way from poverty to influence, getting pulled into the city's mounting tension between mages and the templars who police them.\n\nUnlike the multi-region journey of the first game, the story stays centered on Kirkwall and its surroundings, framed as a story being recounted after the fact by the dwarf Varric to an inquisitor investigating what really happened. Combat is faster and more streamlined than its predecessor, with companions like Varric, Isabela, and Merrill each carrying their own subplots and loyalties.\n\nHawke's choices throughout -- who to side with, who to protect, who to let fall -- gradually push the city, and the wider conflict between mages and templars, toward a breaking point.",
    "45410997": "Dragon Age: Inquisition begins with a massive rift torn open in the sky, spilling demons across the land after a catastrophic explosion destroys a peace conference and kills nearly everyone attending. The player, marked with a mysterious power to seal such rifts, becomes the sole leader of a rebuilt Inquisition tasked with restoring order.\n\nThe game moves to large, open regions to explore rather than a handful of hub areas, letting the player recruit agents, build keeps, and manage the Inquisition's growing influence between story missions. A returning cast of companions, from war-hardened templars to sharp-tongued spies, offer differing views on how the Inquisition should wield its new authority.\n\nBehind the immediate crisis lies a larger threat tied to an ancient enemy seeking godhood, and the choices made in confronting both the rifts and the Inquisition's own politics shape the state of Thedas by the story's end.",
    "454108C0": "Dragon Age: Origins opens with the player character being recruited into the Grey Wardens, an ancient order dedicated to fighting the corrupted monsters known as darkspawn, just as a new Blight threatens to overrun the kingdom of Ferelden. One of six possible origin stories sets up who the character is and why they joined before the main plot begins.\n\nWith the Wardens' leadership wiped out through betrayal, the player must travel Ferelden gathering old allies and rival factions -- dwarves, elves, mages, and feuding nobles -- willing to fight in the coming battle, all while political intrigue threatens to fracture the kingdom from within.\n\nCombat plays out with a party of up to four characters, pausable to issue tactical orders, and companions react to the player's choices with approval or disapproval that shapes relationships and unlocks personal storylines over the course of the campaign.",
    "5553087E": "Driver: San Francisco puts undercover detective John Tanner back behind the wheel after a crash leaves him in a coma, chasing his old nemesis Charles Jericho through a dreamlike version of San Francisco. The story leans into that dream logic rather than shying away from it.\n\nThe game's signature mechanic is Shift, which lets Tanner leave his own body and instantly possess any other car on the road, turning chases into puzzles about picking the right vehicle at the right moment -- cutting off a suspect, ramming a blocker into their path, or simply outmaneuvering traffic from a totally different car.\n\nMissions mix scripted story chases with an open city full of side activities and a large roster of licensed cars to unlock, all wrapped in a plot that blurs the line between what's really happening and what's just in Tanner's head.",
    "565507E0": "Eragon adapts the fantasy novel of the same name, casting the player as farm boy Eragon after he discovers a mysterious blue stone that hatches into a dragon, Saphira. As one of the last Dragon Riders, Eragon is drawn into a rebellion against the tyrannical King Galbatorix, who wiped out the Riders years before.\n\nThe game is a straightforward action title built around sword combat, magic spells, and Eragon's growing bond with Saphira, including airborne combat sequences where players take control of the dragon directly to battle enemies from the sky.\n\nFollowing the broad strokes of the book's plot, Eragon travels from his home village into the wider world, training with the elderly storyteller Brom and gradually coming to understand both his own destiny and the war being waged around him.",
    "4D530A87": "Fable Anniversary is a high-definition remaster of the original Fable, following a young hero from childhood in the village of Oakvale through his rise as a legendary figure in Albion after tragedy strikes his home. Along the way he trains at the Heroes' Guild and takes on contracts that shape both his skills and his reputation.\n\nThe defining idea is a morality system where good and evil choices visibly change the hero over time -- a righteous path brings a halo-like glow and admiring townsfolk, while cruelty brings horns, scars, and a darker world reacting in kind. Diet, tattoos, and battle scars all layer onto this same visual transformation.\n\nCombat blends melee weapons, ranged attacks, and Will magic, freely mixed together in real time, while side quests, marriage, and property ownership let players build a life in Albion alongside the main quest to confront the game's central villain, Jack of Blades.",
    "4D5307F1": "Fable II is set five centuries after the original, opening with a young orphan whose sister is killed by a corrupt lord after being tricked into wishing on a magical artifact. Left for dead, the child survives, trains as a Hero, and spends years growing in power to track down those responsible.\n\nThe game keeps Fable's good-versus-evil morality system, now paired with a loyal dog companion who fights alongside the hero, digs up buried treasure, and reacts to the player's moral choices. Property ownership, marriage, and family expand significantly, letting players build an actual life across Albion's towns between adventures.\n\nCombat streamlines melee, ranged, and magic into simple, combinable inputs, making it easy to blend styles in real time, while the story builds toward a confrontation with the mysterious figure who orchestrated the hero's childhood tragedy.",
    "4D5308D6": "Fable III casts the player as the younger sibling of Albion's tyrannical King Logan, forced into hiding after refusing to go along with his brutal policies. Gathering allies from across the kingdom, the player leads a revolution to overthrow Logan and take the throne.\n\nThe second half of the game flips the premise: now ruling as King or Queen, the player must keep campaign promises to the people who helped them win the crown while raising the funds needed to defend Albion from a threat revealed only after Logan's fall, forcing hard choices between idealism and survival.\n\nThe familiar morality and relationship systems return, now extended into the throne room itself, where royal decrees carry the same weight as the personal choices that shaped the hero's rise to power.",
    "4D5309C9": "Forza Horizon takes the Forza series out of closed circuits and into an open world, built around a fictional cars-and-music festival spread across Colorado. Players compete in a mix of point-to-point road races, off-road events, and street battles against rival racers to rise through the festival's ranks.\n\nUnlike the simulation-focused mainline Forza games, Horizon leans into a looser, more arcade-friendly handling model while keeping a large and detailed roster of licensed cars, letting the world itself -- highways, backroads, and open fields -- double as a playground between scheduled events.\n\nA day-night cycle and dynamic weather shift racing conditions throughout the festival, and side activities like speed traps, showcase events, and hidden challenges reward players for simply driving around and exploring the map.",
    "4D530AA4": "Forza Horizon 2 moves the festival across Southern Europe, spanning sun-drenched coastal roads in France and mountain passes in Italy. The open map is significantly larger than the original, with the road-trip structure of driving between regional festival sites forming the backbone of the campaign.\n\nDynamic weather returns as a headline feature, with storms rolling across the map in real time and changing how cars handle from one moment to the next, alongside the returning day-night cycle. The game continues Horizon's blend of accessible arcade handling with a deep, licensed car roster drawn from the wider Forza series.\n\nA drivatar system fills the open road with AI recreations of other players' driving styles, and cross-country point-to-point routes let players carve their own paths between checkpoints rather than following a single fixed line.",
    "443607D8": "Game of Thrones - A Telltale Games Series is an episodic narrative adventure set alongside the events of the HBO show, following House Forrester, a minor noble family whose fortunes collapse in the chaos after the Red Wedding. Playing across several family members, the story follows their struggle to survive amid stronger, more ruthless houses.\n\nAs with other Telltale games, play centers on branching dialogue choices and quick-time action sequences rather than traditional combat or exploration, with decisions carrying weight across episodes and shaping which characters live, who the Forresters ally with, and how their story ultimately plays out.\n\nFamiliar faces from the show, including Tyrion Lannister, Cersei Lannister, and Margaery Tyrell, appear throughout as the Forresters navigate the political minefields of King's Landing, the Wall, and their home in the North.",
    "545408B8": "Grand Theft Auto: San Andreas follows Carl \"CJ\" Johnson, who returns to the fictional state of San Andreas after his mother's murder, only to be dragged back into the gang life he left behind by corrupt cops and old rivalries. His journey stretches across the cities of Los Santos, San Fierro, and Las Venturas.\n\nThe open world expands well beyond earlier games in the series, adding a whole state to explore by car, bike, plane, and boat, alongside RPG-style additions like customizable stats for stamina, strength, and driving skill, gang territory control, and a wardrobe and physique that respond to what CJ eats and how he trains.\n\nThe story moves from street-level gang warfare into wider criminal conspiracies involving corrupt government agents, all while CJ tries to reunite his family and reclaim the neighborhood he grew up in.",
    "545407F2": "Grand Theft Auto IV follows Niko Bellic, an Eastern European immigrant who arrives in Liberty City chasing his cousin Roman's promises of the American Dream, only to find debt, dead-end jobs, and old enemies from his past waiting for him. Working odd jobs for the city's criminal underworld, Niko is gradually pulled into deeper and more violent territory.\n\nThe game reworks the series' open-world formula around a more grounded, weightier tone than its predecessors, with a Liberty City modeled closely on New York and a physics-driven approach to driving, combat, and character movement. A basic morality thread runs through Niko's choices, including who lives and who dies at key story junctures.\n\nMultiplayer modes let players free-roam the city or compete in deathmatches and races, while Niko's own arc wrestles with whether he can leave violence behind or whether it will define him regardless of what he wants.",
    "4156081A": "Guitar Hero World Tour expands the rhythm-game formula into a full band, adding drums and vocals alongside the series' familiar guitar peripheral. Up to four players can perform together in real time, each judged on their own instrument while contributing to a shared band score.\n\nA setlist of licensed rock songs spans decades of music, playable through a career mode that has the band touring and unlocking new venues, or through quick single-song sessions for casual play. Difficulty scales per instrument, letting a mixed-skill group play together without everyone needing the same experience level.\n\nThe game's Music Studio lets players compose and record their own original songs using in-game instruments and share them online, a first for the series at the time, extending play well past the included setlist.",
    "4D5307E6": "Halo 3 closes out the original trilogy, picking up with Master Chief returning to Earth as the Covenant invasion reaches its climax and the ancient Forerunner installations known as Halos threaten to be activated again. Alongside the Arbiter and old allies, Chief has to stop the fanatical Prophet of Truth before he can fire the rings and end all sentient life in the galaxy.\n\nCombat continues the series' sandbox approach, mixing human and alien weapons, vehicles, and the Flood's ever-present threat across large, open combat spaces built for improvisation. Equipment items like bubble shields and gravity lifts add new tactical options on top of the returning two-weapon loadout and regenerating shields.\n\nForge mode returns as a powerful map and game-mode editor, and the game's multiplayer, including large squad battles and a Theater mode for reviewing and sharing match footage, became a defining part of the Xbox 360 era.",
    "4D530919": "Halo 4 picks up Master Chief's story four years after Halo 3, waking from cryo-sleep aboard the drifting ship Forward Unto Dawn to find it under attack. Together with the AI Cortana, whose degrading mental state becomes a central emotional thread, Chief is pulled into a new conflict against the Prometheans, ancient robotic guardians tied to a ruthless Forerunner intelligence called the Didact.\n\nDeveloped by 343 Industries rather than series creator Bungie, the game keeps Halo's core sandbox combat while introducing new enemy types and weapons unique to the Prometheans, alongside a more overtly personal, character-driven story than earlier entries focused on Chief and Cortana's bond.\n\nMultiplayer is reworked around the War Games simulation and a new asymmetric mode called Spartan Ops, delivering episodic co-op missions that continue the story beyond the campaign's ending.",
    "4D5309B1": "Halo: Combat Evolved Anniversary is a remaster of the game that launched the series and helped define console first-person shooters, following Master Chief and the AI Cortana after their ship crash-lands near a massive ringworld called Halo. What begins as a fight against the alien Covenant turns into a discovery of the ring's true, planet-sterilizing purpose.\n\nThe remaster rebuilds the game's visuals while leaving the original level design and combat sandbox untouched, letting players switch between updated and classic graphics on the fly with a single button press to compare the two directly.\n\nSkulls hidden throughout the campaign modify gameplay in various ways for repeat playthroughs, and Xbox Live-enabled online multiplayer was added for classic maps that originally only supported local or LAN play, bringing the original's competitive scene onto modern infrastructure.",
    "4D53085B": "Halo: Reach is a prequel set just before the original Halo, following Noble Team, a squad of Spartan supersoldiers defending the planet Reach as the Covenant launches a full-scale invasion. Unlike Master Chief's story, Reach is a fight the defenders are ultimately known to lose, giving the campaign a grim, last-stand tone from the outset.\n\nPlayers control a customizable Spartan, Noble Six, joining an established squad with their own personalities and relationships rather than acting as a lone hero, which shapes how the story's losses land as the campaign progresses toward Reach's fall.\n\nThe game introduces armor abilities like jetpacks and sprint that change how encounters play out, alongside a large suite of multiplayer and customization options, including Firefight survival mode and one of the series' most extensive character customization systems to date.",
    "45410819": "Harry Potter and the Order of the Phoenix follows Harry's fifth year at Hogwarts, where the Ministry of Magic's denial that Voldemort has returned leads to a hostile new administration at the school under Dolores Umbridge. In response, Harry secretly forms Dumbledore's Army to teach his fellow students real defensive magic.\n\nThe game opens Hogwarts and its grounds into a more explorable space than earlier entries, letting players wander freely between classes and story missions while casting spells to solve environmental puzzles, unlock secret passages, and battle enemies in real time.\n\nAs Harry trains his classmates in secret and Umbridge's control over the school tightens, the story builds toward the Ministry of Magic itself and Harry's first direct confrontation with Voldemort since their encounter at the end of the previous school year.",
    "454107FA": "Harry Potter and the Half-Blood Prince follows Harry's sixth year at Hogwarts, where Dumbledore begins privately tutoring him using memories that reveal Voldemort's past and how he became the dark wizard he is. Meanwhile, Harry inherits an old potions textbook annotated by a mysterious \"Half-Blood Prince,\" whose handwritten tricks give him an edge in class.\n\nGameplay continues the series' free-roaming exploration of Hogwarts, layering in potion-brewing challenges tied to the textbook's notes alongside the returning spell-casting and dueling mechanics used to solve puzzles and fend off enemies around the castle grounds.\n\nAs teenage romances and rivalries play out against the backdrop of a growing sense of dread, the story builds toward Dumbledore and Harry's dangerous mission to retrieve a crucial piece of Voldemort's soul, with consequences that darken the rest of the series.",
    "454108F9": "Harry Potter and the Deathly Hallows Part 1 leaves Hogwarts behind as Harry, Ron, and Hermione go on the run, tasked with tracking down and destroying the Horcruxes that anchor Voldemort to life while the wizarding world falls further under Death Eater control.\n\nThe shift away from a school setting brings a corresponding shift in gameplay, trading corridor exploration for stealth-focused sequences and cover-based dueling as the trio moves between hideouts, avoiding capture while investigating leads on the Horcruxes and the title's mysterious Deathly Hallows.\n\nWith few allies left to turn to and Voldemort's forces closing in, the story follows the trio's isolation and growing desperation as the war reaches its darkest point, setting up the direct continuation into the series' final chapter.",
    "45410955": "Harry Potter and the Deathly Hallows Part 2 covers the series' final chapter, as Harry, Ron, and Hermione track down the last of Voldemort's Horcruxes before returning to a Hogwarts under siege for one last stand against the Death Eaters.\n\nThe game builds to the large-scale Battle of Hogwarts, mixing spell-dueling combat across the castle's halls and grounds with pivotal story sequences drawn directly from the book and film, including Harry's final direct confrontations with Voldemort.\n\nAs old allies and enemies converge on the school, the story resolves the series' central conflict, closing out Harry's journey from an unknowing boy wizard to the one person capable of ending Voldemort's reign for good.",
    "4B4E085E": "Metal Gear Solid V: The Phantom Pain sends Big Boss, badly wounded and newly awoken from a nine-year coma, into the deserts of Afghanistan and the mountains of Africa to rebuild his private army and hunt down the shadowy group responsible for destroying his previous outfit.\n\nThe game opens up the series' stealth-action formula into a large open world, letting players approach outposts and bases with a mix of scouting, silent takedowns, vehicle infiltration, and full firefights, while the Mother Base management layer lets captured soldiers and looted resources be funneled into growing Diamond Dogs' strength back at base.\n\nAlongside the main campaign, side ops, buddy companions like the sniper Quiet and the robotic Metal Gear D-Walker, and an evolving day-night, weather-affected battlefield give missions room to be replayed and approached differently each time, tying into a story that digs into themes of revenge, identity, and the cost of war.",
    "4B4E083C": "Metal Gear Solid: Peace Walker is set in 1974 Costa Rica, where Naked Snake, now going by Militaires Sans Frontieres commander, investigates a mysterious weapon called Peace Walker and the private army responsible for a string of attacks in the region.\n\nBuilt originally for handheld hardware, Peace Walker structures its stealth-action gameplay into bite-sized missions that can be tackled solo or in cooperative play, layering in base-building and soldier recruitment systems that let players grow Snake's private army, research new weapons and gear, and customize loadouts before heading back into the field.\n\nThe game bridges the story between Snake Eater and the founding of Outer Heaven, deepening the series' themes around private military companies and nuclear deterrence while introducing gameplay systems, like Mother Base management, that would later be expanded significantly in The Phantom Pain.",
    "454107D9": "Need for Speed: Most Wanted drops players into the fictional Rockport City as a street racer who arrives to find their prized car impounded, kicking off a climb through a ranked list of fifteen rival racers known as the Blacklist while evading an increasingly aggressive police force.\n\nRacing blends open-world exploration with circuit, sprint, and drag events, but the game's signature draw is its pursuit system, where cops chase down racers using roadblocks, spike strips, and helicopter support, and players can rack up bounty, ram through checkpoints, and find hiding spots to shake heat between races.\n\nBeating each Blacklist rival unlocks their car and a step closer to the top spot, all set against a career structure of milestones, customization options, and a story told through live-action cutscenes that frame the escalating rivalry between the player and the city's top racers.",
    "45410876": "Need for Speed: Undercover casts the player as an undercover cop infiltrating a street racing ring and smuggling operation across the fictional Tri-City Bay area, working their way up through the criminal organization to expose its leaders while racing against rivals on both sides of the law.\n\nThe open-world map is built around circuit races, sprints, drag events, and highway battles, alongside cop chases that echo the pursuit-driven design of Most Wanted, with a heavy customization system for tuning and visually modifying an extensive roster of licensed cars.\n\nLive-action video cutscenes tie the missions together into a crime story of betrayal and deep cover work, with the player's progress and reputation growing through the ranks of the syndicate as they build toward taking down the operation from within.",
    "425307D1": "The Elder Scrolls IV: Oblivion opens with the player escaping the imperial sewers after the assassination of Emperor Uriel Septim, thrust into a plot to close the Oblivion Gates that are letting daedric forces pour into the province of Cyrodiil.\n\nAs an open-world action RPG, Oblivion lets players ignore the main questline entirely in favor of joining guilds like the Fighters Guild, Mages Guild, Thieves Guild, or the murderous Dark Brotherhood, each with its own branching quest chain, while a flexible class and skill system lets a character's abilities grow based on how they actually play, whether that's sneaking, spellcasting, or swinging a blade.\n\nCyrodiil itself is dotted with dungeons, ruins, caves, and towns to stumble into off the beaten path, and the main story's Oblivion Gates task players with fighting through daedric-corrupted realms to seal the invasion, all building toward a final confrontation that decides the fate of the empire's throne.",
    "58410960": "Portal: Still Alive puts players in the shoes of Chell, a test subject navigating a series of puzzle chambers inside the Aperture Science facility under the watch of GLaDOS, an AI whose calm, encouraging narration slides steadily into something far more menacing as the tests continue.\n\nThe core mechanic revolves around the portal gun, which fires two linked openings onto flat surfaces that let players and objects travel instantly between them, turning each chamber into a physics puzzle about momentum, timing, and spatial reasoning rather than combat. This Xbox 360 release bundles the original campaign with a set of additional advanced and challenge maps exclusive to this version, extending the puzzle content beyond the base game.\n\nAs Chell progresses deeper into the facility, the sparse story unfolds through GLaDOS's dialogue and environmental details scattered through the test chambers, building toward a memorable escape from the testing track and a confrontation that has become one of the most quoted moments in the genre.",
    "4D5307D1": "Project Gotham Racing 3 is a launch-era Xbox 360 racer that sends players through real-world cities like New York, London, Tokyo, and Las Vegas, racing high-performance cars across circuit, cityscape, and time-trial events built around the series' signature Kudos scoring system.\n\nRather than rewarding raw finishing position alone, Kudos is earned through stylish driving, drifting, near-misses, and clean cornering, and that score doubles as the game's currency for unlocking new cars and events, pushing players to drive with flair rather than just aggression.\n\nThe game also leaned into the online capabilities of the new console generation, offering it as one of the more prominent Xbox Live racing experiences of its time, letting the Kudos-driven scoring and car culture carry over into competitive online play alongside the single-player World Tour progression.",
    "4D5307F9": "Project Gotham Racing 4 continues the series' city-based, Kudos-driven racing across an expanded roster of real-world locations, adding motorcycles to the vehicle lineup alongside cars and introducing dynamic weather and time-of-day changes that visibly affect track conditions and racing lines.\n\nThe career mode builds around collecting Kudos and completing events to earn geared vehicle classes and unlock new locations, with the online component pushing further into social features, letting players form racing clubs, take photos in a dedicated photo mode, and compete in leaderboard-driven challenges.\n\nA notable feature at the time was Xbox Live Vision camera integration, letting players' photos appear on in-game billboards and driver profiles, tying the game's community-focused online presence directly into the racing experience itself.",
    "584113EE": "R.I.P.D.: The Game is a movie tie-in third-person shooter based on the film of the same name, casting players as an officer of the Rest In Peace Department, a police force made up of deceased cops tasked with hunting down souls who evade the afterlife and linger on Earth.\n\nGameplay centers on cover-based shooting against Deados, disguised undead criminals, blending standard firearms combat with supernatural gadgets and partner-based team play echoing the film's buddy-cop dynamic, as players work through city environments hunting escaped souls.\n\nAs a licensed tie-in, the game follows the broad strokes of the movie's premise and tone, offering a straightforward action shooter experience aimed at fans of the film's supernatural police procedural setup rather than an expansive original story.",
    "53450839": "Resonance of Fate is a steampunk role-playing game set on Basel, an artificial tower-city built after a mysterious toxin rendered the world's surface uninhabitable, following three mercenaries, Zephyr, Leanne, and Vashyron, who take on jobs to survive within its rigid class structure.\n\nCombat departs sharply from typical JRPG design, built around a hexagonal grid where characters weave between direct melee Hero attacks and rapid gunfire Scratch damage, chaining together tri-attack combos while managing ammunition types, positioning, and a health system where wounds only heal from Hero damage, forcing constant tactical tradeoffs.\n\nOutside of battle, players explore Basel's tower districts and the surrounding wasteland via a hexagonal overworld map, taking on bounty-hunter style jobs that reveal the city's oppressive caste system and the trio's own uncertain place within it, building toward a story about found family and self-determination in a rigidly stratified world.",
    "575207F5": "Scene It? Bright Lights! Big Screen! is a movie-trivia party game built for the Xbox 360's controller and Big Button Pad accessory, testing players' knowledge of films through video clips, still images, and audio cues spanning classic and contemporary Hollywood movies.\n\nRounds mix multiple-choice questions with more visual challenges like identifying a film from a blurred image or a rearranged plot summary, and the game supports both couch multiplayer with up to four players using the Big Button Pad controllers and standard single-player play through standard controllers.\n\nAs part of the broader Scene It? franchise that grew out of a physical DVD board game, this entry leans on licensed film clips and a game-show presentation style to turn movie trivia into a party format, with categories and question types varying to keep matches from feeling repetitive.",
    "4D530832": "Scene It? Lights, Camera, Action! is an earlier entry in the movie-trivia party series, bringing the franchise's mix of film clips, still frames, and question rounds to the Xbox 360 with support for the Big Button Pad controllers for group play.\n\nPlayers answer questions across a range of formats, from straightforward multiple-choice trivia to visual puzzles built from freeze-framed movie scenes, drawing on a broad library of licensed clips spanning decades of Hollywood film to challenge both casual viewers and dedicated movie buffs.\n\nDesigned as a living-room party game, it emphasizes quick pick-up-and-play rounds and simultaneous local multiplayer over any deep single-player structure, positioning it as a couch-friendly alternative to traditional board game trivia nights.",
    "4B4E0845": "Silent Hill: HD Collection bundles remastered versions of Silent Hill 2 and Silent Hill 3, two of the series' most acclaimed survival horror entries, updated with higher-resolution visuals for the Xbox 360 while keeping the original games' fixed-camera exploration and puzzle-driven structure intact.\n\nSilent Hill 2 follows James Sunderland into the fog-shrouded town after receiving a letter from his deceased wife, unraveling a deeply psychological story about grief and guilt as he confronts monsters that embody his own repressed trauma, while Silent Hill 3 follows Heather Mason as she's drawn into a cult conspiracy tied directly to the events of the first game.\n\nBoth games lean on limited resources, disorienting fog and darkness, and unsettling creature design over action-heavy combat, and this collection preserves that atmosphere-first approach to horror even as it updates the presentation, though the remaster's audio and lighting changes were a point of some debate among longtime fans of the originals.",
    "4541080F": "The Orange Box compiles five Valve titles onto one Xbox 360 disc: Half-Life 2 and its two episodic follow-ups, Episode One and Episode Two, alongside the puzzle game Portal and the multiplayer shooter Team Fortress 2, offering a broad cross-section of Valve's output in a single package.\n\nThe Half-Life 2 trilogy follows Gordon Freeman's fight against the alien Combine occupation of Earth, mixing physics-driven combat via the gravity gun with vehicle sections and set-piece battles across City 17 and its surrounding regions, while Portal introduces the portal gun puzzle mechanic later spun off into its own full release, and Team Fortress 2 delivers class-based team combat with nine distinct character roles across objective-driven maps.\n\nTogether the collection served as many console players' introduction to Valve's narrative-driven shooters and Portal's now-influential puzzle design, packaging story-driven single-player campaigns alongside a competitive multiplayer shooter in one disc.",
    "584111FA": "The Simpsons Arcade Game is a faithful port of the 1991 Konami beat-'em-up, bringing back the classic four-player brawler where Homer, Marge, Bart, and Lisa fight through the streets of Springfield to rescue baby Maggie from the diamond-smuggling Smithers and Mr. Burns.\n\nGameplay sticks closely to the genre's roots, with each Simpson family member wielding a distinct weak attack and special move as players punch, kick, and swing improvised weapons through waves of enemies across side-scrolling stages themed around recognizable Springfield locations, all rendered in the show's signature art style.\n\nThis re-release preserves the original arcade experience while adding online co-op for up to four players, letting the beat-'em-up be played the way it was designed, as a couch or online co-op romp through a irreverent, Simpsons-flavored take on the genre's over-the-top boss fights and cartoon violence.",
    "4E4D0855": "The Witcher 2: Assassins of Kings casts players once again as Geralt of Rivia, a mutant monster hunter drawn into a political conspiracy after being framed for the assassination of King Foltest, forcing him to hunt down the real killer while unraveling a plot involving kingslayers, secret societies, and warring factions.",
    "C0DE9999": "XeXMenu is not a retail game but a homebrew dashboard and executable launcher used on modified Xbox 360 consoles, providing a lightweight interface for browsing and running unsigned .xex files, backups, and other homebrew applications outside of the standard Xbox dashboard.\n\nVersion 1.1 offers a simple file-browser style menu for navigating storage devices connected to the console, letting users launch homebrew tools, emulators, or game backups directly without needing to go through official channels, which made it a common utility on jailbroken and RGH/JTAG consoles.\n\nAs a system utility rather than a piece of entertainment software, its role in a game library is functional: it sits alongside actual titles as a quick-access launcher for the broader homebrew and backup ecosystem that these modified consoles support."
}


def get_demo_games() -> List[Dict]:
    """Returns the fake console library as UI-ready dictionaries."""
    games = []
    for g in _DEMO_GAMES:
        title_id = _normalize(g["title_id"])
        db_id = _normalize(g["db_id"])
        desc = g.get("description") or DEMO_GAME_SYNOPSES.get(title_id, f"{g['title_name']} — demo library entry for UI/UX testing.")
        games.append({
            "title_name": g["title_name"],
            "description": desc,
            "publisher": g.get("publisher", ""),
            "developer": g.get("developer", ""),
            "release_date": g.get("release_date", ""),
            "title_id": title_id,
            "media_id": _normalize(g.get("media_id", "00000000")),
            "db_id": db_id,
            "disc_num": 1,
            "folder_path": f"{title_id}_{db_id}",
            "boxart_file": f"GC{title_id}.asset",
            "background_file": f"BK{title_id}.asset",
            "icon_banner_file": f"GL{title_id}.asset",
            "screenshots_file": f"SS{title_id}.asset",
        })
    games.sort(key=lambda x: x["title_name"].lower())
    return games


def find_demo_game(title_id: str, db_id: Optional[str] = None) -> Optional[Dict]:
    title_id = _normalize(title_id)
    db_norm = _normalize(db_id) if db_id else None
    for g in get_demo_games():
        if g["title_id"] == title_id and (db_norm is None or g["db_id"] == db_norm):
            return g
    return None


def _color_for(title_id: str) -> tuple:
    idx = 0
    try:
        idx = int(_normalize(title_id), 16) % len(_PALETTE)
    except ValueError:
        idx = sum(ord(c) for c in title_id) % len(_PALETTE)
    return _PALETTE[idx]


def _demo_index(title_id: str) -> int:
    """Stable per-game index used to vary which assets appear 'missing'."""
    try:
        return int(_normalize(title_id), 16)
    except ValueError:
        return sum(ord(c) for c in title_id)


def _has_asset(title_id: str, kind: str) -> bool:
    """Deterministically decide whether a demo game 'has' a given asset so the
    library grid shows a realistic mix of complete and incomplete games."""
    seed = _demo_index(title_id)
    mapping = {
        "boxart": seed % 7 != 0,
        "background": seed % 5 != 0,
        "icon": seed % 4 != 0,
        "banner": seed % 6 != 0,
        "screenshots": seed % 3 != 0,
    }
    return mapping.get(kind, True)


def get_demo_asset_status(games: List[Dict]) -> Dict:
    """Mirrors /api/library/asset-status using fake completeness data."""
    results = []
    for game in games:
        title_id = _normalize(game.get("title_id"))
        if title_id == "00000000":
            continue
        results.append({
            "title_id": title_id,
            "db_id": _normalize(game.get("db_id") or "00000001"),
            "title_name": game.get("title_name", "Unknown"),
            "has_boxart": _has_asset(title_id, "boxart"),
            "has_background": _has_asset(title_id, "background"),
            "has_icon": _has_asset(title_id, "icon"),
            "has_banner": _has_asset(title_id, "banner"),
            "screenshot_count": 4 if _has_asset(title_id, "screenshots") else 0,
        })

    total = len(results)
    missing_any = sum(
        1 for r in results
        if not r["has_boxart"] or not r["has_background"]
        or not r["has_icon"] or not r["has_banner"] or r["screenshot_count"] == 0
    )
    return {
        "success": True,
        "total": total,
        "missing_any": missing_any,
        "complete": total - missing_any,
        "results": results,
    }


# Target pixel sizes for each generated placeholder category.
_CATEGORY_SIZES = {
    "boxart": (300, 420),
    "background": (1280, 720),
    "icon_banner": {0: (64, 64), 1: (420, 96)},
    "screenshots": (640, 360),
}


def _load_font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("Arial.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, box, text: str, font, fill=(255, 255, 255, 235)):
    x0, y0, x1, y1 = box
    ox = oy = 0
    try:
        tb = draw.textbbox((0, 0), text, font=font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        ox, oy = tb[0], tb[1]
    except Exception:
        tw, th = draw.textsize(text, font=font)
    cx = x0 + (x1 - x0 - tw) / 2 - ox
    cy = y0 + (y1 - y0 - th) / 2 - oy
    draw.text((cx, cy), text, font=font, fill=fill)


def _generate_image(category: str, asset_index: int, title_id: str, title_name: str) -> Image.Image:
    base = _color_for(title_id)
    if category == "icon_banner":
        size = _CATEGORY_SIZES["icon_banner"].get(1 if asset_index == 1 else 0, (64, 64))
    else:
        size = _CATEGORY_SIZES.get(category, (400, 400))

    w, h = size
    img = Image.new("RGBA", (w, h), base + (255,))
    draw = ImageDraw.Draw(img)

    # Opaque vertical gradient from the base colour to a darker shade for depth.
    dark = tuple(max(0, c - 60) for c in base)
    for y in range(h):
        t = y / max(1, h - 1)
        row = tuple(int(base[i] + (dark[i] - base[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=row + (255,))

    label = title_name
    kind_label = category.replace("_", " ").title()
    if category == "icon_banner":
        kind_label = "Icon" if asset_index != 1 else "Banner"
    elif category == "screenshots":
        kind_label = f"Screenshot {asset_index + 1}"

    small = category == "icon_banner" and asset_index != 1
    if small:
        font = _load_font(max(10, h // 4))
        _draw_centered(draw, (0, 0, w, h), (title_name[:1] or "?").upper(), font)
    else:
        title_font = _load_font(max(14, min(w, h) // 12))
        kind_font = _load_font(max(11, min(w, h) // 22))
        _draw_centered(draw, (10, 10, w - 10, h - 40), label, title_font)
        _draw_centered(draw, (10, h - 44, w - 10, h - 12), f"DEMO · {kind_label}", kind_font,
                       fill=(255, 255, 255, 180))

    draw.rectangle([(0, 0), (w - 1, h - 1)], outline=(255, 255, 255, 255), width=2)
    return img


def generate_placeholder_png(category: str, asset_index: int, title_id: str,
                             title_name: Optional[str] = None) -> bytes:
    """Generates a labelled placeholder PNG for the given asset slot."""
    if not title_name:
        game = find_demo_game(title_id)
        title_name = game["title_name"] if game else f"Title {(_normalize(title_id))}"
    img = _generate_image(category, asset_index, title_id, title_name)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _preview_kind(category: str, asset_index: int) -> str:
    if category == "icon_banner":
        return "banner" if asset_index == 1 else "icon"
    if category == "screenshots":
        return "screenshots"
    return category


# Maps a UI category/slot to the search category understood by XboxUnityClient.
_SEARCH_CATEGORY = {
    "boxart": "boxart",
    "background": "background",
    "icon": "icon",
    "banner": "banner",
    "screenshots": "screenshots",
}


def _fetch_real_art(category: str, asset_index: int, title_id: str,
                    title_name: str) -> Optional[bytes]:
    """Attempts to fetch real artwork for a slot from Xbox Unity / online sources.

    Boxart comes from xboxunity.net (via ``XboxUnityClient.search_covers``); the
    other categories fall back to the same online media search used by the app's
    normal "search online" feature. Returns None if nothing usable is found.
    """
    if not network_enabled():
        return None

    cache_key = (_normalize(title_id), category, asset_index)
    with _REAL_ART_LOCK:
        if cache_key in _REAL_ART_CACHE:
            return _REAL_ART_CACHE[cache_key]

    result_bytes: Optional[bytes] = None
    try:
        # Imported lazily so demo_data has no hard dependency on network stack.
        from aurora_engine.integrations.xbox_unity import XboxUnityClient

        kind = _preview_kind(category, asset_index)
        search_cat = _SEARCH_CATEGORY.get(kind, "boxart")
        items = XboxUnityClient.search_media(title_name, category=search_cat)

        if items:
            # For screenshots pick the Nth distinct result; otherwise the first.
            pick_index = asset_index if category == "screenshots" else 0
            pick_index = min(pick_index, len(items) - 1)
            image_url = items[pick_index].get("image_url") or items[0].get("image_url")
            if image_url:
                result_bytes = XboxUnityClient.download_image(image_url)
    except Exception:
        result_bytes = None

    with _REAL_ART_LOCK:
        _REAL_ART_CACHE[cache_key] = result_bytes
    return result_bytes


def demo_preview_png(category: str, asset_index: int, title_id: str) -> Optional[bytes]:
    """Returns PNG bytes for a slot, or None when the fake game is intentionally
    'missing' that asset (so the UI shows its empty state).

    Prefers real cover art fetched from Xbox Unity / online sources, and falls
    back to a labelled generated placeholder when offline or when no art exists.
    """
    title_id = _normalize(title_id)
    kind = _preview_kind(category, asset_index)
    if not _has_asset(title_id, kind):
        return None
    # Screenshots use Aurora's entry layout: the frontend requests indices 5+
    # (entry 5 = first screenshot). Expose the first 4 as demo art.
    if category == "screenshots":
        local = asset_index - 5 if asset_index >= 5 else asset_index
        if local < 0 or local >= 4:
            return None

    game = find_demo_game(title_id)
    title_name = game["title_name"] if game else f"Title {title_id}"

    real = _fetch_real_art(category, asset_index, title_id, title_name)
    if real:
        return real

    return generate_placeholder_png(category, asset_index, title_id, title_name)
