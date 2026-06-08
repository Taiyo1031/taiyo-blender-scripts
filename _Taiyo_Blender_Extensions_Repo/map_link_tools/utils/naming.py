import re


BLENDER_NUMERIC_SUFFIX_RE = re.compile(r"\.\d{3}$")


def has_blender_numeric_suffix(name):
    return bool(BLENDER_NUMERIC_SUFFIX_RE.search(name or ""))


def remove_blender_numeric_suffix(name):
    return BLENDER_NUMERIC_SUFFIX_RE.sub("", name or "")


def short_list(names, limit=6):
    names = [name for name in names if name]
    if not names:
        return ""
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown += f", ... +{len(names) - limit}"
    return shown
