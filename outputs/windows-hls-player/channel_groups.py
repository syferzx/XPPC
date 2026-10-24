"""Presentation-only TV categories; never changes availability or entitlements."""
import re
import unicodedata

def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '')) if not unicodedata.combining(c)).casefold()

def enabled(value):
    return value is True or str(value).lower() in ('1','true','yes')

def channel_groups(channel):
    name=normalized(channel.get('name',''))
    explicit=next((str(channel[k]).strip() for k in ('categoryName','groupName','genre') if isinstance(channel.get(k),str) and channel[k].strip()),'')
    adult=any(enabled(channel.get(k)) for k in ('isAdult','adult')) or bool(re.search(r'(?:^|\W)(?:\+18|18\+|adultos|xxx|playboy|venus|penthouse|hustler|sextreme|sexy\s*hot|private\s*tv)(?:\W|$)',name))
    # "Adult Swim" is an entertainment brand, not an adult-content flag.
    premium=any(enabled(channel.get(k)) for k in ('isPremium','premium','isVip')) or bool(re.search(r'\b(?:premium|hbo|cinemax|starz)\b',name))
    if adult:primary='Adultos +18'
    elif explicit:primary=explicit[:80]
    elif re.search(r'\b(?:espn|fox sports|tnt sports|sports?|deport\w*|tyc|tdn|tudn|dazn|dsports|directv sports|ecdf|cdf|cdo|nba|nfl|mlb|nhl|f1|golf|tennis|ufc|wwe|bein|win\s*\+|liga\w*)\b',name):primary='Deportes'
    elif re.search(r'\b(?:noticias|news|cnn|bbc world|france\s*24|dw|euronews|ntn\s*24|a24|c5n|tn|24\s*horas|milenio)\b',name):primary='Noticias'
    elif re.search(r'\b(?:disney|nick\w*|cartoon|boomerang|tooncast|baby\w*|discovery kids|kids|paka\s*paka|clan|toons?)\b',name):primary='Infantiles'
    elif re.search(r'\b(?:hbo|cinemax|cine\w*|cinema|movies?|film\w*|series|axn|amc|fx|fxx|tnt|tcm|space|sony|warner|universal|paramount|studio\s*universal|golden|star\s*channel|a\s*&\s*e|adult swim|syfy|starz|netflix)\b',name):primary='Cine y series'
    elif re.search(r'\b(?:discovery|history|national geographic|nat\s*geo|animal planet|document\w*|investigation|love nature|smithsonian|science|odisea)\b',name):primary='Documentales'
    elif re.search(r'\b(?:mtv\w*|vh1|musica|music\w*|htv|telehit|ritmoson|concert\w*|mezzo)\b',name):primary='Música'
    elif re.search(r'\b(?:ewtn|enlace|relig\w*|catolic\w*|cristian\w*|esperanza|3abn|bethel|nuevo tiempo)\b',name):primary='Religiosos'
    elif re.search(r'\b(?:granja|reality|gran hermano|casa de los famosos|eventos)\b',name):primary='Eventos y reality'
    else:primary='General y variedades'
    groups=[primary]
    if premium and primary!='Premium':groups.append('Premium')
    return groups
