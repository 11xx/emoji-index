#!/usr/bin/env python3
"""Rebuild emoji labels and keywords into a cleaner search index.

The original data was model-enriched, then manually corrected in a few places.
This pass keeps the useful shape of that data while making the final files
deterministic: each row gets a compact keyword set derived from the CLDR name,
Unicode group/subgroup, curated aliases, and variant descriptors.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path


FIELD_SEP = " | "
TARGETS = (Path("emojis.txt"), Path("emojis-full.txt"))
MAX_KEYWORDS = 28
MIN_KEYWORDS = 10

SKIN_TONES = (
    "light skin tone",
    "medium-light skin tone",
    "medium skin tone",
    "medium-dark skin tone",
    "dark skin tone",
)
HAIR_VARIANTS = ("red hair", "curly hair", "white hair", "bald")
VARIANT_DESCRIPTORS = set(SKIN_TONES + HAIR_VARIANTS)

BANNED_KEYWORDS = {
    "action",
    "actions",
    "concept",
    "concepts",
    "emoji",
    "emoji context",
    "emoji index",
    "emoji list",
    "emoji lookup",
    "emoji meaning",
    "emoji picker",
    "emoji search",
    "emoji suggestion",
    "emoji use",
    "emoji usage",
    "emojis",
    "emotion",
    "emotional expression",
    "expression",
    "fuzzy",
    "fuzzy search",
    "internet term",
    "line 1",
    "line 2",
    "context",
    "meaning",
    "partial match",
    "picker",
    "qwen",
    "search",
    "search term",
    "searchable",
    "slangy",
    "subgroup",
    "symbol group",
    "synonym",
    "synonym for peek",
    "terminal",
    "terminal search",
    "tofi",
    "tone",
    "usage",
    "usage in conversation",
    "usage in texting",
    "use",
    "vibe",
    "vibes",
    "visual",
    "visual cue",
    "visual signal",
}

TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "for",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

TYPO_FIXES = {
    "allright": "alright",
    "brain storming": "brainstorming",
    "calmness": "calm",
    "cheekiness": "cheeky",
    "confidentwoman": "confident woman",
    "cutey": "cute",
    "dark-skinned": "dark skin",
    "emotionnal": "emotional",
    "emoticon": "emoji",
    "goodvibes": "good vibes",
    "haircolor": "hair color",
    "hopefulsign": "hopeful",
    "hopefulness": "hope",
    "joyfulness": "joy",
    "laughing": "laugh",
    "light-hearted": "lighthearted",
    "luckyness": "luck",
    "mediumlight": "medium-light",
    "monke": "monkey",
    "okayie": "okay",
    "outcomehope": "hopeful outcome",
    "positivevibes": "good vibes",
    "redhaired": "red-haired",
    "self": "self-expression",
    "sneakily": "sneaky",
    "sovereignity": "sovereignty",
    "successfull": "successful",
    "surrealism": "surreal",
    "wishfulthinking": "wishful thinking",
    "wishy": "wish",
}

GROUP_KEYWORDS = {
    "Smileys & Emotion": [
        "reaction",
        "chat",
        "feeling",
        "mood",
        "emotion",
        "texting",
        "message",
    ],
    "People & Body": [
        "person",
        "body",
        "gesture",
        "people",
        "human",
        "nonverbal",
        "identity",
    ],
    "Animals & Nature": [
        "nature",
        "animal",
        "wildlife",
        "outdoors",
        "creature",
        "environment",
    ],
    "Food & Drink": [
        "food",
        "drink",
        "meal",
        "snack",
        "cooking",
        "restaurant",
        "taste",
    ],
    "Travel & Places": [
        "travel",
        "place",
        "location",
        "map",
        "journey",
        "destination",
        "navigation",
    ],
    "Activities": [
        "activity",
        "event",
        "game",
        "sport",
        "hobby",
        "play",
        "competition",
    ],
    "Objects": [
        "object",
        "tool",
        "item",
        "device",
        "everyday",
        "utility",
        "thing",
    ],
    "Symbols": [
        "symbol",
        "sign",
        "marker",
        "button",
        "status",
        "interface",
        "indicator",
    ],
    "Flags": [
        "flag",
        "identity",
        "pride",
        "banner",
        "symbol",
        "signal",
        "representation",
    ],
}

SUBGROUP_KEYWORDS = {
    "alphanum": ["letters", "numbers", "input", "text", "keyboard", "button", "character"],
    "animal-amphibian": ["frog", "amphibian", "pond", "wetland"],
    "animal-bird": ["bird", "wings", "feather", "fly", "wildlife"],
    "animal-bug": ["bug", "insect", "crawl", "garden", "tiny"],
    "animal-mammal": ["mammal", "pet", "zoo", "wild", "cute", "farm"],
    "animal-marine": ["ocean", "sea", "marine", "fish", "water", "aquatic"],
    "animal-reptile": ["reptile", "lizard", "snake", "scales", "wild"],
    "arrow": ["arrow", "direction", "move", "point", "navigate", "up", "down", "left", "right"],
    "arts & crafts": ["art", "craft", "creative", "paint", "make", "design"],
    "av-symbol": ["media", "playback", "audio", "video", "control", "button", "interface"],
    "award-medal": ["award", "medal", "prize", "winner", "achievement", "honor"],
    "body-parts": ["body", "anatomy", "health", "sense", "human", "physical"],
    "book-paper": ["book", "paper", "document", "read", "write", "notes"],
    "cat-face": ["cat", "feline", "pet", "cute", "playful", "reaction", "meme"],
    "clothing": ["clothing", "fashion", "wear", "outfit", "style", "accessory"],
    "computer": ["computer", "tech", "device", "screen", "keyboard", "software"],
    "country-flag": ["flag", "country", "nation", "national", "identity", "pride", "heritage"],
    "currency": ["money", "currency", "finance", "payment", "exchange"],
    "dishware": ["dish", "table", "serve", "kitchen", "restaurant", "meal"],
    "drink": ["drink", "beverage", "cup", "sip", "party", "refreshment"],
    "emotion": ["feeling", "emotion", "heart", "mood", "love", "reaction"],
    "event": ["event", "party", "celebration", "holiday", "occasion", "fun"],
    "face-affection": ["love", "affection", "heart", "crush", "warm", "sweet", "flirt"],
    "face-concerned": ["worry", "concern", "sad", "anxious", "fear", "stress", "upset"],
    "face-costume": ["costume", "silly", "disguise", "character", "fantasy", "playful"],
    "face-glasses": ["glasses", "cool", "nerd", "smart", "inspect", "look", "style"],
    "face-hand": ["hand", "gesture", "cover", "shy", "quiet", "reaction"],
    "face-hat": ["hat", "party", "cowboy", "celebrate", "style"],
    "face-negative": ["angry", "mad", "frustrated", "curse", "devil", "mean", "annoyed"],
    "face-neutral-skeptical": ["neutral", "skeptical", "doubt", "awkward", "silence", "unsure"],
    "face-sleepy": ["sleep", "tired", "relief", "rest", "calm", "bored", "nap"],
    "face-smiling": ["smile", "happy", "joy", "laugh", "friendly", "cheerful", "positive"],
    "face-tongue": ["tongue", "silly", "playful", "tease", "joke", "food", "yum"],
    "face-unwell": ["sick", "ill", "unwell", "health", "dizzy", "overwhelmed"],
    "family": ["family", "parent", "child", "home", "relationship", "together"],
    "flag": ["flag", "banner", "symbol", "identity", "pride", "signal"],
    "food-asian": ["food", "asian", "rice", "noodles", "bowl", "takeout", "meal"],
    "food-fruit": ["fruit", "sweet", "fresh", "healthy", "produce", "juice"],
    "food-prepared": ["meal", "dinner", "lunch", "cooking", "restaurant", "hungry"],
    "food-sweet": ["sweet", "dessert", "candy", "treat", "sugar", "snack"],
    "food-vegetable": ["vegetable", "produce", "garden", "healthy", "fresh", "cooking"],
    "game": ["game", "play", "dice", "cards", "toy", "puzzle", "fun"],
    "gender": ["gender", "identity", "person", "sign", "symbol"],
    "geometric": ["shape", "color", "circle", "square", "marker", "block", "status"],
    "hand-fingers-closed": ["hand", "fist", "gesture", "approval", "solidarity", "signal"],
    "hand-fingers-open": ["hand", "palm", "wave", "stop", "reach", "gesture", "signal"],
    "hand-fingers-partial": ["hand", "finger", "gesture", "sign", "signal", "nonverbal"],
    "hand-prop": ["hand", "write", "selfie", "prop", "gesture", "tool"],
    "hand-single-finger": ["point", "finger", "direction", "gesture", "up", "down", "left", "right"],
    "hands": ["hands", "gesture", "pray", "clap", "shake", "support", "thanks"],
    "heart": ["heart", "love", "affection", "care", "romance", "support", "feeling"],
    "hotel": ["hotel", "travel", "stay", "sleep", "service", "accommodation"],
    "household": ["home", "household", "clean", "furniture", "daily", "utility"],
    "keycap": ["keycap", "number", "keyboard", "digit", "button", "input"],
    "light & video": ["light", "video", "camera", "film", "bright", "record"],
    "lock": ["lock", "security", "privacy", "safe", "password", "access"],
    "mail": ["mail", "message", "email", "send", "receive", "inbox", "outbox"],
    "math": ["math", "calculate", "operator", "number", "sign", "formula"],
    "medical": ["medical", "health", "doctor", "hospital", "medicine", "care"],
    "money": ["money", "cash", "bank", "finance", "payment", "wealth"],
    "monkey-face": ["monkey", "playful", "shy", "secret", "avoid", "mischief"],
    "music": ["music", "song", "note", "sound", "melody", "audio"],
    "musical-instrument": ["instrument", "music", "play", "band", "sound", "concert"],
    "office": ["office", "work", "desk", "document", "organize", "supplies"],
    "other-object": ["object", "item", "utility", "everyday", "misc"],
    "other-symbol": ["symbol", "sign", "mark", "status", "notice", "indicator"],
    "person": ["person", "human", "identity", "individual", "adult", "people"],
    "person-activity": ["activity", "movement", "routine", "self-care", "body", "motion"],
    "person-fantasy": ["fantasy", "magic", "myth", "monster", "story", "character"],
    "person-gesture": ["gesture", "person", "hello", "no", "yes", "bow", "raise hand"],
    "person-resting": ["rest", "sleep", "relax", "bed", "bath", "quiet"],
    "person-role": ["job", "work", "career", "profession", "uniform", "worker"],
    "person-sport": ["sport", "athlete", "competition", "training", "team", "movement"],
    "person-symbol": ["symbol", "silhouette", "people", "identity", "sign"],
    "phone": ["phone", "call", "mobile", "contact", "device", "communication"],
    "place-building": ["building", "city", "place", "architecture", "landmark", "location"],
    "place-geographic": ["geography", "landscape", "mountain", "island", "desert", "map"],
    "place-map": ["map", "location", "compass", "direction", "navigation", "travel"],
    "place-other": ["place", "location", "landmark", "site", "travel", "destination"],
    "place-religious": ["religion", "worship", "temple", "church", "mosque", "sacred"],
    "plant-flower": ["flower", "plant", "garden", "bloom", "nature", "spring"],
    "plant-other": ["plant", "tree", "leaf", "nature", "green", "growth"],
    "punctuation": ["punctuation", "mark", "emphasis", "question", "exclamation", "text"],
    "religion": ["religion", "faith", "spiritual", "worship", "sacred", "symbol"],
    "science": ["science", "lab", "experiment", "chemistry", "research", "tech"],
    "sky & weather": ["weather", "sky", "sun", "moon", "cloud", "rain", "storm"],
    "sound": ["sound", "audio", "volume", "speaker", "listen", "noise"],
    "sport": ["sport", "game", "athlete", "team", "competition", "fitness"],
    "subdivision-flag": ["flag", "region", "national", "identity", "heritage", "place"],
    "time": ["time", "clock", "schedule", "timer", "wait", "deadline", "calendar"],
    "tool": ["tool", "build", "fix", "repair", "work", "hardware"],
    "transport-air": ["air", "flight", "plane", "airport", "travel", "fly"],
    "transport-ground": ["vehicle", "road", "drive", "transport", "commute", "traffic"],
    "transport-sign": ["sign", "traffic", "warning", "direction", "road", "public"],
    "transport-water": ["boat", "ship", "water", "travel", "sea", "transport"],
    "warning": ["warning", "alert", "danger", "caution", "notice", "attention"],
    "writing": ["write", "pen", "pencil", "edit", "note", "draw"],
    "zodiac": ["zodiac", "astrology", "horoscope", "star", "sign", "birth"],
}

NAME_KEYWORDS = {
    "beating heart": ["heartbeat", "pulse", "alive", "love", "emotion"],
    "broken heart": ["heartbreak", "sad", "breakup", "hurt", "grief"],
    "call me hand": ["call", "phone", "shaka", "hang loose", "contact", "reach out"],
    "cowboy hat face": ["cowboy", "western", "yeehaw", "confidence", "swagger", "hat"],
    "crossed fingers": ["luck", "good luck", "hope", "wish", "fingers crossed", "please"],
    "distorted face": ["distorted", "warped", "inflated", "huh", "confused", "anxious"],
    "face holding back tears": ["teary", "moved", "touched", "grateful", "emotional"],
    "face vomiting": ["vomit", "puke", "nausea", "gross", "disgust", "sick"],
    "face with bags under eyes": ["tired", "exhausted", "sleepy", "burnout", "worn out"],
    "face with hand over mouth": ["giggle", "oops", "secret", "shy", "embarrassed"],
    "face with monocle": ["inspect", "scrutinize", "curious", "hmm", "detective"],
    "face with open eyes and hand over mouth": ["gasp", "oops", "shocked", "secret", "caught"],
    "face with peeking eye": ["peek", "peeking", "curious", "nervous", "scared", "hide"],
    "face with rolling eyes": ["eye roll", "sarcasm", "annoyed", "whatever", "disbelief"],
    "face with spiral eyes": ["dizzy", "overwhelmed", "confused", "mind blown", "chaos"],
    "face with symbols on mouth": ["swearing", "cursing", "angry", "rage", "censored"],
    "diving mask": ["scuba", "snorkel", "diving", "underwater", "ocean", "swim"],
    "hairy creature": ["bigfoot", "sasquatch", "cryptid", "monster", "hairy", "myth"],
    "hand with index finger and thumb crossed": ["finger heart", "money gesture", "snap", "small heart", "korean heart"],
    "heart on fire": ["passion", "desire", "intense", "burning love", "obsessed"],
    "hot dog": ["hot dog", "frankfurter", "sausage", "cookout", "baseball", "street food"],
    "hot face": ["hot", "heat", "sweat", "fever", "spicy", "thirsty"],
    "love-you gesture": ["i love you", "sign language", "asl", "love", "hand sign", "affection"],
    "melting face": ["melt", "embarrassed", "overwhelmed", "heat", "awkward", "collapse"],
    "middle finger": ["rude", "insult", "flip off", "anger", "defiance"],
    "money-mouth face": ["money", "cash", "rich", "profit", "greed", "payday"],
    "nauseated face": ["nausea", "sick", "gross", "disgust", "queasy", "vomit"],
    "ok hand": ["okay", "ok", "approval", "perfect", "chef kiss", "agree"],
    "partying face": ["party", "celebrate", "birthday", "confetti", "fun", "hype"],
    "pleading face": ["please", "beg", "puppy eyes", "cute", "help", "soft"],
    "phoenix": ["rebirth", "rise", "mythical", "fire", "flame"],
    "raised back of hand": ["raise hand", "stop", "question", "volunteer", "attention"],
    "red heart": ["love", "heart", "romance", "care", "affection"],
    "rice ball": ["rice ball", "onigiri", "rice", "snack", "japanese food", "lunch"],
    "rolling on the floor laughing": ["rofl", "lmao", "lol", "hilarious", "laugh", "funny"],
    "shaking face": ["shaking", "shock", "quake", "panic", "overwhelmed", "vibrate"],
    "sign of the horns": ["rock", "metal", "concert", "horns", "rebellion", "party"],
    "skull": ["dead", "dying laughing", "dark humor", "spooky", "death"],
    "slightly smiling face": ["smile", "polite", "awkward", "passive aggressive", "fine"],
    "smiling face with halo": ["angel", "innocent", "blessed", "good", "pure"],
    "smiling face with hearts": ["love", "adore", "cute", "warm", "affection"],
    "smiling face with heart-eyes": ["heart eyes", "crush", "love", "adore", "obsessed"],
    "thumbs down": ["dislike", "no", "reject", "disapprove", "bad"],
    "thumbs up": ["like", "yes", "agree", "approve", "good", "okay"],
    "upside-down face": ["sarcasm", "irony", "awkward", "silly", "passive aggressive"],
    "victory hand": ["peace", "victory", "win", "two", "v sign", "success"],
    "wastebasket": ["trash", "garbage", "bin", "delete", "remove", "discard"],
    "wireless": ["wifi", "network", "internet", "signal", "connection", "router"],
    "zipper-mouth face": ["secret", "quiet", "hush", "silent", "no comment", "sealed"],
    "zombie": ["undead", "horror", "brain", "tired", "walking dead"],
}

LABEL_OVERRIDES = {
    "beans": "Marks beans, legumes, food prep, or a simple meal",
    "eight-thirty": "Shows an 8:30 time, deadline, or schedule",
    "eleven-thirty": "Shows an 11:30 time, deadline, or schedule",
    "face vomiting": "Shows nausea, grossed-out disgust, or getting sick",
    "first quarter moon face": "Adds a dreamy moon mood to night messages",
    "green salad": "Marks a salad, healthy meal, or fresh food",
    "hairy creature": "Represents a cryptid, bigfoot, or strange fantasy creature",
    "nauseated face": "Shows disgust, nausea, sickness, or queasy discomfort",
    "nine-thirty": "Shows a 9:30 time, deadline, or schedule",
    "one-thirty": "Shows a 1:30 time, deadline, or schedule",
    "pig": "Represents pigs, farms, pork, or playful messiness",
    "seven-thirty": "Shows a 7:30 time, deadline, or schedule",
    "woman getting haircut": "Shows a salon visit, haircut, or fresh style",
}

WORD_ALIASES = {
    "angry": ["mad", "rage", "furious"],
    "astonished": ["amazed", "shocked", "surprised"],
    "baby": ["infant", "child", "newborn"],
    "bag": ["purse", "shopping"],
    "baggage": ["luggage", "travel"],
    "ball": [],
    "bank": ["money", "finance"],
    "beach": ["summer", "vacation"],
    "beard": ["facial hair"],
    "beer": ["drink", "bar", "party"],
    "bicycle": ["bike", "cycling"],
    "bird": ["wings", "feather"],
    "birthday": ["party", "cake", "celebrate"],
    "boat": ["ship", "sailing"],
    "book": ["read", "paper"],
    "bottle": ["drink", "water"],
    "bow": ["respect", "thanks", "apology"],
    "bread": ["bakery", "toast"],
    "broken": ["sad", "hurt"],
    "bug": ["insect"],
    "building": ["city", "place"],
    "bus": ["transit", "commute"],
    "button": ["control", "interface"],
    "cake": ["birthday", "dessert"],
    "calendar": ["date", "schedule"],
    "camera": ["photo", "picture"],
    "cane": ["accessibility", "blind", "low vision", "mobility aid"],
    "car": ["auto", "vehicle", "drive"],
    "cat": ["feline", "pet"],
    "celebration": ["party", "festive"],
    "check": ["done", "confirm", "yes"],
    "chicken": ["bird", "poultry"],
    "child": ["kid", "young"],
    "circle": ["round", "shape"],
    "clap": ["applause", "praise"],
    "clock": ["time", "schedule"],
    "closed": ["shut"],
    "cloud": ["weather", "sky"],
    "clown": ["silly", "circus", "joke"],
    "cold": ["freezing", "chill", "winter"],
    "computer": ["pc", "tech"],
    "confetti": ["party", "celebrate"],
    "confused": ["unsure", "puzzled"],
    "cookie": ["dessert", "sweet"],
    "copyright": ["rights", "ownership", "license", "creative work"],
    "cool": ["chill", "stylish"],
    "cowboy": ["western", "yeehaw"],
    "crying": ["sad", "tears"],
    "dance": ["party", "music"],
    "deaf": ["accessibility", "sign language"],
    "diamond": ["gem", "jewel"],
    "dog": ["pet", "canine"],
    "door": ["entrance", "exit"],
    "down": ["below", "lower"],
    "dragon": ["fantasy", "myth"],
    "dress": ["clothing", "fashion"],
    "drink": ["beverage"],
    "drooling": ["hungry", "desire"],
    "eject": ["remove", "exit"],
    "electric": ["power", "energy"],
    "envelope": ["mail", "message"],
    "exclamation": ["urgent", "emphasis"],
    "eye": ["look", "watch", "see"],
    "face": ["reaction"],
    "factory": ["industry", "work"],
    "family": ["home", "parents", "children"],
    "fearful": ["scared", "afraid"],
    "fire": ["hot", "flame"],
    "flag": ["banner"],
    "flower": ["bloom", "garden"],
    "food": ["eat", "meal"],
    "footprints": ["steps", "trail", "tracks", "walking", "path"],
    "football": ["sport", "soccer"],
    "fork": ["eat", "dining"],
    "fountain": ["water", "place"],
    "frog": ["amphibian"],
    "game": ["play"],
    "gear": ["settings", "machine"],
    "gift": ["present", "birthday"],
    "glasses": ["eyewear", "look"],
    "globe": ["world", "earth", "global"],
    "grinning": ["grin", "smile", "happy", "laugh"],
    "guitar": ["music", "instrument"],
    "hair": ["hairstyle"],
    "hand": ["gesture", "signal"],
    "heart": ["love", "care"],
    "hospital": ["medical", "health"],
    "hot": ["heat", "warm", "spicy"],
    "house": ["home"],
    "hundred": ["100", "perfect"],
    "hushed": ["quiet", "silent"],
    "ice": ["cold", "frozen"],
    "japanese": ["japan"],
    "key": ["lock", "password"],
    "kiss": ["love", "romance"],
    "laughing": ["laugh", "funny"],
    "left": ["back", "previous"],
    "letter": ["mail", "message"],
    "light": ["bright"],
    "lock": ["secure", "privacy"],
    "loud": ["noise", "volume"],
    "mailbox": ["mail", "post"],
    "mask": ["face covering", "cover", "protection"],
    "medal": ["award", "winner"],
    "microphone": ["mic", "record", "sing"],
    "mobile": ["phone", "cell"],
    "money": ["cash", "finance"],
    "moon": ["night", "sky"],
    "motor": ["engine", "vehicle"],
    "mouse": ["rodent", "computer"],
    "mouth": ["speak", "talk"],
    "movie": ["film", "cinema"],
    "music": ["song", "audio"],
    "neutral": ["blank", "meh"],
    "night": ["dark", "sleep"],
    "office": ["work"],
    "open": ["available"],
    "paint": ["art", "color"],
    "paper": ["document", "page"],
    "party": ["celebrate", "fun"],
    "pen": ["write"],
    "pencil": ["write", "draw"],
    "person": ["human", "individual"],
    "phone": ["call"],
    "pig": ["farm", "pork"],
    "pin": ["location", "marker"],
    "pizza": ["food", "slice"],
    "plane": ["flight", "airplane"],
    "police": ["cop", "law"],
    "question": ["ask", "help"],
    "rabbit": ["bunny"],
    "radio": ["music", "broadcast"],
    "rain": ["weather", "wet"],
    "raised": ["up"],
    "recycling": ["recycle", "sustainability", "environment"],
    "red": ["color"],
    "relieved": ["calm", "peace"],
    "restaurant": ["food", "dining"],
    "right": ["next", "forward"],
    "robot": ["bot", "automation"],
    "rocket": ["launch", "space"],
    "rose": ["flower", "romance"],
    "sad": ["unhappy", "down"],
    "saluting": ["respect", "honor"],
    "school": ["education", "class"],
    "scissors": ["cut"],
    "shaking": ["vibrate", "tremble"],
    "shield": ["protect", "security"],
    "ship": ["boat", "sea"],
    "shopping": ["buy", "store"],
    "shushing": ["quiet", "hush"],
    "sleeping": ["sleep", "nap"],
    "smiling": ["smile", "happy"],
    "snow": ["winter", "cold"],
    "soccer": ["football", "sport"],
    "sparkles": ["shine", "magic"],
    "speaker": ["sound", "volume"],
    "speech": ["talk", "chat"],
    "square": ["shape", "block"],
    "star": ["favorite", "night"],
    "sun": ["day", "bright"],
    "sweat": ["nervous", "relief"],
    "syringe": ["medical", "vaccine"],
    "taxi": ["cab", "transport"],
    "telephone": ["phone", "call"],
    "thumbs": ["approval", "like"],
    "ticket": ["event", "entry"],
    "toilet": ["bathroom", "restroom"],
    "tongue": ["silly", "taste"],
    "tool": ["fix", "repair"],
    "train": ["rail", "transport"],
    "tree": ["forest", "nature"],
    "trophy": ["winner", "award"],
    "truck": ["delivery", "vehicle"],
    "umbrella": ["rain", "weather"],
    "up": ["above", "higher"],
    "video": ["film", "record"],
    "volleyball": ["sport", "team", "court", "serve", "spike"],
    "warning": ["alert", "caution"],
    "water": ["drink", "wet"],
    "wave": ["hello", "goodbye"],
    "winking": ["wink", "flirt"],
    "woman": ["female", "person"],
    "world": ["global", "earth"],
    "writing": ["write"],
}

CONTEXT_ALIAS_BLOCKS = {
    ("Food & Drink", "ball"),
    ("Food & Drink", "dog"),
}

COMPONENT_KEYWORDS = {
    "U+2695": ("medical", "doctor", "nurse", "medicine", "hospital", "clinic"),
    "U+2696": ("scales", "justice", "law", "legal", "court"),
    "U+2708": ("airplane", "plane", "flight", "aviation", "airport"),
    "U+1F33E": ("farm", "farming", "agriculture", "crop", "field", "harvest"),
    "U+1F373": ("chef", "cooking", "kitchen", "food", "meal", "pan"),
    "U+1F37C": ("bottle", "milk", "nursing"),
    "U+1F384": ("christmas", "holiday", "santa", "festive"),
    "U+1F393": ("graduation", "cap", "school", "college", "university", "education", "study"),
    "U+1F3A4": ("microphone", "mic", "music", "song", "stage", "performance"),
    "U+1F3A8": ("palette", "art", "paint", "creative", "design", "drawing"),
    "U+1F3EB": ("school", "classroom", "education", "class", "teaching", "learning"),
    "U+1F3ED": ("factory", "manufacturing", "production", "industrial", "machine"),
    "U+1F4BB": ("computer", "laptop", "pc", "coding", "programmer", "developer", "software"),
    "U+1F4BC": ("briefcase", "business", "corporate", "desk", "professional"),
    "U+1F525": ("fire", "flame", "burning"),
    "U+1F527": ("wrench", "tool", "repair", "fix", "maintenance", "hardware"),
    "U+1F52C": ("microscope", "science", "lab", "research", "experiment", "chemistry"),
    "U+1F680": ("rocket", "space", "launch", "orbit", "spacecraft"),
    "U+1F692": ("firetruck", "fire engine", "fire", "emergency", "rescue"),
    "U+1F9BA": ("accessibility", "assistance", "service animal", "guide dog", "vest"),
    "U+1FA70": ("ballet shoes", "shoes", "dance", "performance", "stage"),
    "U+1FA79": ("bandage", "healing", "recovery", "repair"),
    "U+2744": ("snow", "cold", "winter", "arctic"),
}

SEMANTIC_KEYWORD_RULES = (
    (
        re.compile(r"\b(laugh(?:ing|ter|s|ed)?|giggl(?:e|ing)?|lol|lmao|rofl|hilarious|funny|humou?r(?:ous)?|jokes?|amusement|amused)\b"),
        ("laugh", "funny", "joke", "humor"),
    ),
    (
        re.compile(r"\b(joy|joyful|happy|happiness|cheer(?:ful)?|delight(?:ed)?|glad)\b"),
        ("joy", "happy", "cheerful"),
    ),
    (
        re.compile(r"\b(cry|crying|cries|cried|sob(?:bing)?|teary|tearful|sad|sadness|upset|sorrow)\b"),
        ("cry", "tears", "sad"),
    ),
    (
        re.compile(r"\b(love|affection(?:ate)?|romantic|romance|adore|heart|hearts|crush)\b"),
        ("love", "affection", "heart"),
    ),
    (
        re.compile(r"\b(angry|anger|mad|rage|furious|frustrat(?:ed|ion)?|annoy(?:ed|ance)?|irritat(?:ed|ion)?|exasperat(?:ed|ion)?)\b"),
        ("angry", "frustrated", "annoyed"),
    ),
    (
        re.compile(r"\b(surprise|surprised|surprising|shock(?:ed)?|gasp|astonish(?:ed)?|startled|stunned)\b"),
        ("surprise", "shock", "gasp"),
    ),
    (
        re.compile(r"\b(tired|exhaust(?:ed|ion)?|sleep|sleepy|sleeping|weary|yawn(?:ing)?|rest|resting)\b"),
        ("tired", "sleep", "rest"),
    ),
    (
        re.compile(r"\b(confus(?:e|ed|ion)|doubt(?:ful)?|unsure|skeptic(?:al)?|uncertain|puzzled)\b"),
        ("confused", "doubt", "unsure"),
    ),
    (
        re.compile(r"\b(disgust(?:ed|ing)?|gross|nausea|nauseated|queasy|sick)\b"),
        ("disgust", "gross", "sick"),
    ),
    (
        re.compile(r"\b(scared|fear|fearful|afraid|terror|nervous|anxious|anxiety|worry|worried)\b"),
        ("fear", "scared", "anxious", "worry"),
    ),
)

LAUGH_CRY_CONTEXT_RE = re.compile(
    r"\b(laugh(?:ing|ter|s|ed)?|giggl(?:e|ing)?|lol|lmao|rofl|hilarious|funny|humou?r(?:ous)?|joy|joyful|happy)\b"
)
SAD_CONTEXT_RE = re.compile(r"\b(sad|sadness|upset|sorrow|distress|grief|heartbreak)\b")

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


@dataclass(frozen=True)
class Row:
    emoji: str
    group: str
    subgroup: str
    name: str
    label: str
    keywords: str
    codepoints: str | None

    @classmethod
    def parse(cls, line: str) -> "Row":
        parts = line.rstrip("\n").split(FIELD_SEP)
        if len(parts) not in {6, 7}:
            raise ValueError(f"expected 6 or 7 fields, got {len(parts)}: {line!r}")
        codepoints = parts[6] if len(parts) == 7 else None
        return cls(*parts[:6], codepoints)

    def format(self, label: str, keywords: list[str]) -> str:
        fields = [
            self.emoji,
            self.group,
            self.subgroup,
            self.name,
            label,
            ", ".join(keywords),
        ]
        if self.codepoints:
            fields.append(self.codepoints)
        return FIELD_SEP.join(fields)


def ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalize_text(value: str) -> str:
    value = value.replace("’", "'").replace("“", "").replace("”", "")
    value = value.replace("&", " and ")
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


def canonical_keyword(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("okay", "ok") if value == "okay hand" else value
    value = TYPO_FIXES.get(value, value)
    value = re.sub(r"\bemoji\b", "", value)
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    return TYPO_FIXES.get(value, value)


def split_variant_name(name: str) -> tuple[str, list[str]]:
    if ": " not in name or name.startswith(("flag:", "keycap:")):
        return name, []

    base, raw_descriptors = name.split(": ", 1)
    descriptors = [normalize_text(part) for part in raw_descriptors.split(",")]
    descriptors = [part for part in descriptors if part]
    if descriptors and all(part in VARIANT_DESCRIPTORS for part in descriptors):
        return base, descriptors
    return name, []


def useful_tokens(value: str) -> list[str]:
    value = ascii_fold(normalize_text(value))
    value = value.replace("o'clock", "oclock")
    raw = re.split(r"[^a-z0-9+#]+", value)
    return [tok for tok in raw if tok and tok not in TOKEN_STOPWORDS]


def name_phrases(name: str) -> list[str]:
    folded = ascii_fold(normalize_text(name))
    cleaned = re.sub(r"[^a-z0-9+#]+", " ", folded).strip()
    pieces = cleaned.split()
    phrases: list[str] = []

    if 1 < len(pieces) <= 4:
        phrases.append(" ".join(pieces))
    if "u s" in cleaned:
        phrases.extend(["us", "usa", "united states"])
    if re.search(r"\bst\b", cleaned):
        phrases.append(re.sub(r"\bst\b", "saint", cleaned))
    if "turkiye" in cleaned:
        phrases.append("turkey")
    if "cote d ivoire" in cleaned:
        phrases.append("ivory coast")
    return phrases


def time_keywords(base_name: str) -> list[str]:
    normalized = normalize_text(base_name).replace("o'clock", "oclock")
    normalized = normalized.replace("-", " ")
    words = normalized.split()
    if not words:
        return []

    hour = NUMBER_WORDS.get(words[0])
    if hour is None:
        return []

    if "thirty" in words:
        return [f"{hour}:30", "half past", "thirty", "schedule", "time"]
    if "oclock" in words or "o'clock" in words:
        return [f"{hour}:00", f"{hour} oclock", "hour", "schedule", "time"]
    return []


def label_is_bad(label: str) -> bool:
    lowered = label.lower()
    return (
        "natural 6" in lowered
        or "line 1" in lowered
        or "must differ meaningfully" in lowered
        or "emoji picker" in lowered
        or "fuzzy search" in lowered
        or len(label) > 120
    )


def template_label(row: Row, base_name: str) -> str:
    clean = normalize_text(base_name)
    if row.group == "Flags" and clean.startswith("flag:"):
        place = base_name.split(":", 1)[1].strip()
        return f"Represents {place} identity, location, pride, or belonging"
    if row.group == "Smileys & Emotion":
        return f"Shows {clean} as a quick chat reaction"
    if row.group == "People & Body":
        return f"Represents {clean} in gestures, people, or identity"
    if row.group == "Animals & Nature":
        return f"Represents {clean} in nature, animals, or outdoor contexts"
    if row.group == "Food & Drink":
        return f"Marks {clean} for food, drink, meals, or cravings"
    if row.group == "Travel & Places":
        return f"Marks {clean} for travel, places, time, or weather"
    if row.group == "Activities":
        return f"Represents {clean} for games, sports, events, or hobbies"
    if row.group == "Objects":
        return f"Represents {clean} as an everyday object or tool"
    if row.group == "Symbols":
        return f"Marks {clean} as a sign, status, control, or marker"
    return f"Represents {clean} in quick visual communication"


def curate_label(row: Row, base_name: str) -> str:
    key = normalize_text(base_name)
    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]

    label = re.sub(r"\s+", " ", row.label).strip()
    label = label.rstrip(".")
    if label_is_bad(label):
        return template_label(row, base_name)
    return label


def append_keyword(result: list[str], seen: set[str], value: str) -> None:
    kw = canonical_keyword(value)
    if not kw or kw in BANNED_KEYWORDS:
        return
    if kw in TOKEN_STOPWORDS:
        return
    if len(kw) < 2 and kw not in {"ok", "no"}:
        return
    if len(kw.split()) > 4:
        return
    if kw in seen:
        return
    seen.add(kw)
    result.append(kw)


def append_many(result: list[str], seen: set[str], values: list[str] | tuple[str, ...]) -> None:
    for value in values:
        append_keyword(result, seen, value)


def semantic_keywords(row: Row, base_name: str) -> list[str]:
    if row.group != "Smileys & Emotion":
        return []

    text = normalize_text(f"{base_name} {row.label}")
    result: list[str] = []
    for pattern, keywords in SEMANTIC_KEYWORD_RULES:
        if pattern.search(text):
            if (
                keywords == ("cry", "tears", "sad")
                and LAUGH_CRY_CONTEXT_RE.search(text)
                and not SAD_CONTEXT_RE.search(text)
            ):
                result.extend(("cry", "tears"))
                continue
            result.extend(keywords)
    return result


def component_keywords(row: Row) -> list[str]:
    if not row.codepoints or "U+200D" not in row.codepoints:
        return []

    result: list[str] = []
    for codepoint in row.codepoints.split():
        result.extend(COMPONENT_KEYWORDS.get(codepoint, ()))
    return result


def keyword_candidates(row: Row, base_name: str, descriptors: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    name_key = normalize_text(base_name)

    append_many(result, seen, NAME_KEYWORDS.get(name_key, []))
    append_many(result, seen, semantic_keywords(row, base_name))
    append_many(result, seen, name_phrases(base_name))
    append_many(result, seen, useful_tokens(base_name))

    for token in useful_tokens(base_name):
        if (row.group, token) in CONTEXT_ALIAS_BLOCKS:
            continue
        if name_key == "hot dog" and token in {"hot", "dog"}:
            continue
        append_many(result, seen, WORD_ALIASES.get(token, []))

    append_many(result, seen, component_keywords(row))

    if row.subgroup == "time":
        append_many(result, seen, time_keywords(base_name))

    if row.group == "Flags" and name_key.startswith("flag:"):
        place = base_name.split(":", 1)[1].strip()
        append_many(result, seen, name_phrases(place))
        append_many(result, seen, useful_tokens(place))
        append_many(result, seen, ["flag", "country", "nation", "national", "identity", "pride", "heritage", "place"])
        if "united nations" in normalize_text(place):
            append_many(result, seen, ["un", "global", "diplomacy", "peace", "cooperation"])

    append_many(result, seen, SUBGROUP_KEYWORDS.get(row.subgroup, []))
    append_many(result, seen, GROUP_KEYWORDS.get(row.group, []))

    for descriptor in descriptors:
        append_keyword(result, seen, descriptor)
        if descriptor in SKIN_TONES:
            append_many(result, seen, ["skin tone", descriptor.replace(" skin tone", "")])

    return result[:MAX_KEYWORDS]


def curate_rows(rows: list[Row]) -> list[str]:
    base_labels: dict[tuple[str, str, str], str] = {}
    row_meta: list[tuple[Row, str, list[str], tuple[str, str, str]]] = []

    for row in rows:
        base_name, descriptors = split_variant_name(row.name)
        family_key = (row.group, row.subgroup, normalize_text(base_name))
        row_meta.append((row, base_name, descriptors, family_key))
        if not descriptors and family_key not in base_labels:
            base_labels[family_key] = curate_label(row, base_name)

    output: list[str] = []
    for row, base_name, descriptors, family_key in row_meta:
        label = base_labels.get(family_key, curate_label(row, base_name))
        keywords = keyword_candidates(row, base_name, descriptors)
        output.append(row.format(label, keywords))
    return output


def process_file(path: Path, check: bool) -> bool:
    original_text = path.read_text(encoding="utf-8")
    rows = [Row.parse(line) for line in original_text.splitlines() if line.strip()]
    curated = "\n".join(curate_rows(rows)) + "\n"

    if curated == original_text:
        return False

    if check:
        diff = difflib.unified_diff(
            original_text.splitlines(keepends=True),
            curated.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (curated)",
        )
        sys.stdout.writelines(diff)
        return True

    path.write_text(curated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="print the diff without writing files")
    parser.add_argument("paths", nargs="*", type=Path, default=list(TARGETS))
    args = parser.parse_args()

    changed = False
    for path in args.paths:
        changed = process_file(path, args.check) or changed

    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
