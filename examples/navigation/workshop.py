"""A tiny fictional craft workflow used only as navigation evidence."""


def prepare():
    return "paper"


def decorate(material):
    return f"painted {material}"


def build():
    material = prepare()
    return decorate(material)
