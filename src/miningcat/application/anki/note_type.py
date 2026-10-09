from miningcat.application.anki.config import anki
from miningcat.application.mining import preferences
from miningcat.domain.cards import note_type


def note_type_templates() -> dict[str, str]:
    """The front, back and CSS of MiningCat's note type, Mandarin readings in the system chosen in the settings."""
    return note_type.templates({"zh": preferences.reading_system("zh")})


def install_note_type(language: str) -> dict:
    """Creates MiningCat's note type in Anki, or brings it up to date (its templates, and the fields it lacks:
    the user's own fields are kept). Returns its name, fields and what they receive for the cards of `language`."""
    client = anki()
    templates = note_type_templates()
    if note_type.NAME not in client.invoke("modelNames"):
        client.invoke("createModel", modelName=note_type.NAME, inOrderFields=note_type.FIELDS, css=templates["css"],
                      isCloze=False, cardTemplates=[{"Name": note_type.TEMPLATE_NAME, "Front": templates["front"],
                                                     "Back": templates["back"]}])
    else:
        fields = client.invoke("modelFieldNames", modelName=note_type.NAME)
        for name in note_type.FIELDS:
            if name not in fields:
                client.invoke("modelFieldAdd", modelName=note_type.NAME, fieldName=name, index=len(fields))
                fields.append(name)
        client.invoke("updateModelTemplates", model={"name": note_type.NAME, "templates": {
            note_type.TEMPLATE_NAME: {"Front": templates["front"], "Back": templates["back"]}}})
        client.invoke("updateModelStyling", model={"name": note_type.NAME, "css": templates["css"]})
    fields = client.invoke("modelFieldNames", modelName=note_type.NAME)
    known = note_type.field_templates(language)
    return {"model": note_type.NAME, "fields": fields, "templates": {name: known.get(name, "") for name in fields}}
