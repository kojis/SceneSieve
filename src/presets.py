"""Editable English keyword starter lists; not semantic speech classifiers."""
VIDEO={
    'Gore':('drop','gore'),
    'Mature subject matter':('mature','mature subject matter'),
    'Nudity':('person','nudity'),
    'Drugs':('pill','drugs'),
    'Insects and Spiders':('bug','bugs and spiders'),
}
AUDIO={
    'Racial slurs':('speech','nigger, nigga, chink, gook, kike, spic, wetback, raghead, towelhead, beaner'),
    'Derogatory':('speech','fuck, fucking, fucked, fucker, motherfucker, shit, bullshit, bitch, asshole, bastard, damn, goddamn, cunt, dick, piss'),
    'Mature subject matter':('mature','sex, sexual, intercourse, orgasm, pornography, porn, rape, suicide, molestation, molest, incest'),
    'Drugs':('pill','cocaine, heroin, meth, methamphetamine, fentanyl, marijuana, cannabis, weed, ecstasy, ketamine, LSD, crack, overdose'),
}

def value(presets,name):
    if name!='All':return presets[name][1]
    return ', '.join(dict.fromkeys(term.strip() for _,terms in presets.values() for term in terms.split(',')))

def buttons(layout,presets,callback):
    from PySide6.QtWidgets import QComboBox
    from glyphs import icon
    dropdown=QComboBox();dropdown.addItem('Choose a scan shortcut…',None)
    for name,(glyph,_) in [*presets.items(),('All',('all',''))]:dropdown.addItem(icon(glyph),name,name)
    dropdown.setToolTip('Select a preset to fill the search field and start detection')
    dropdown.activated.connect(lambda index:callback(dropdown.itemData(index)) if dropdown.itemData(index) else None)
    layout.addWidget(dropdown)
    return dropdown
