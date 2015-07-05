# -*- coding: utf-8 -*-

import os
import shutil
from xml.etree import cElementTree as ET
import plistlib
import textwrap
import datetime

"""
- add command line functionality (may require a file rename)
- run through the mod times before writing and make sure that
  all registered files exist in the UFO.
- things that need to be improved are marked with "# TO DO"
- is the conversion of numbers coming from plist too naive?
- should unknown attributes be removed in GLIF? they are right now.
- should unknown elements be removed in GLIF? they are right now.
- if removal should be optional, possibly add a -strict option
  that will remove unknown directories/files/elements/attributes
  and fix glaring errors. the places where these could happen
  are being marked with "# INVALID DATA POSSIBILITY"
"""

__version__ = "0a1"
modTimeLibKey = "org.unifiedfontobject.normalizer.modTimes"


class UFONormalizerError(Exception): pass


def normalizeUFO(ufoPath, outputPath=None, onlyModified=True):
    # if the output is going to a different location,
    # duplicate the UFO to the new place and work
    # on the new file instead of trying to reconstruct
    # the file one piece at a time.
    if outputPath is not None:
        duplicateUFO(ufoPath, outputPath)
        ufoPath = outputPath
    # get the UFO format version
    if not subpathExists(ufoPath, "metainfo.plist"):
        raise UFONormalizerError(u"Required metainfo.plist file not in %s." % ufoPath)
    metaInfo = subpathReadPlist(ufoPath, "metainfo.plist")
    formatVersion = metaInfo.get("formatVersion")
    if formatVersion is None:
        raise UFONormalizerError(u"Required formatVersion value not defined in in metainfo.plist in %s." % ufoPath)
    try:
        fV = int(formatVersion)
        formatVersion = fV
    except ValueError:
        raise UFONormalizerError(u"Required formatVersion value not properly formatted in metainfo.plist in %s." % ufoPath)
    if formatVersion > 3:
        raise UFONormalizerError(u"Unsupported UFO format (%d) in %s." % (formatVersion, ufoPath))
    # load the font lib
    if not subpathExists(ufoPath, "lib.plist"):
        fontLib = {}
    else:
        fontLib = subpathReadPlist(ufoPath, "lib.plist")
    # get the modification times
    if onlyModified:
        modTimes = readModTimes(fontLib)
    else:
        modTimes = {}
    # normalize layers
    if formatVersion < 3:
        if subpathExists(ufoPath, "glyphs"):
            normalizeUFO1And2GlyphsDirectory(ufoPath, modTimes)
    else:
        normalizeGlyphsDirectoryNames(ufoPath)
        if subpathExists(ufoPath, "layercontents.plist"):
            layerContents = subpathReadPlist(ufoPath, "layercontents.plist")
            for layerDirectory in layerContents.values():
                normalizeGlyphsDirectory(ufoPath, layerDirectory, onlyModified=onlyModified)
    # normalize top level files
    normalizeMetaInfoPlist(ufoPath, modTimes)
    if subpathExists(ufoPath, "fontinfo.plist"):
        normalizeFontInfoPlist(ufoPath, modTimes)
    if subpathExists(ufoPath, "groups.plist"):
        normalizeGroupsPlist(ufoPath, modTimes)
    if subpathExists(ufoPath, "kerning.plist"):
        normalizeKerningPlist(ufoPath, modTimes)
    if subpathExists(ufoPath, "layercontents.plist"):
        normalizeLayerContentsPlist(ufoPath, modTimes)
    # update the mod time storage, write, normalize
    storeModTimes(fontLib, modTimes)
    subpathWritePlist(fontLib, ufoPath, "lib.plist")
    if subpathExists(ufoPath, "lib.plist"):
        normalizeLibPlist(ufoPath)

# ------
# Layers
# ------

def normalizeGlyphsDirectoryNames(ufoPath):
    """
    non-standard directory names
    -----------------------------
    >>> oldLayers = {
    ...     "public.default" : "glyphs",
    ...     "Sketches" : "glyphs.sketches",
    ... }
    >>> expectedLayers = {
    ...     "public.default" : "glyphs",
    ...     "Sketches" : "glyphs.S_ketches",
    ... }
    >>> _test_normalizeGlyphsDirectoryNames(oldLayers, expectedLayers)
    True

    old directory with same name as new directory
    ---------------------------------------------
    >>> oldLayers = {
    ...     "public.default" : "glyphs",
    ...     "one" : "glyphs.two",
    ...     "two" : "glyphs.three"
    ... }
    >>> expectedLayers = {
    ...     "public.default" : "glyphs",
    ...     "one" : u"glyphs.one",
    ...     "two" : u"glyphs.two"
    ... }
    >>> _test_normalizeGlyphsDirectoryNames(oldLayers, expectedLayers)
    True
    """
    # INVALID DATA POSSIBILITY: directory for layer name may not exist
    # INVALID DATA POSSIBILITY: directory may not be stored in layer contents
    oldLayerMapping = {}
    if subpathExists(ufoPath, "layercontents.plist"):
        layerContents = subpathReadPlist(ufoPath, "layercontents.plist")
        for layerName, layerDirectory in layerContents.items():
            normalizeGlyphsDirectory(ufoPath, layerDirectory)
            oldLayerMapping[layerName] = layerDirectory
    if not oldLayerMapping:
        return
    # INVALID DATA POSSIBILITY: no default layer
    # INVALID DATA POSSIBILITY: public.default used for directory other than "glyphs"
    newLayerMapping = {}
    newLayerDirectories = set()
    for layerName, oldLayerDirectory in sorted(oldLayerMapping.items()):
        if oldLayerDirectory == "glyphs":
            newLayerDirectory = "glyphs"
        else:
            newLayerDirectory = userNameToFileName(unicode(layerName), newLayerDirectories, prefix="glyphs.")
        newLayerDirectories.add(newLayerDirectory)
        newLayerMapping[layerName] = newLayerDirectory
    # don't do a direct rename because an old directory
    # may have the same name as a new directory.
    fromTempMapping = {}
    for index, (layerName, newLayerDirectory) in enumerate(newLayerMapping.items()):
        oldLayerDirectory = oldLayerMapping[layerName]
        if newLayerDirectory == oldLayerDirectory:
            continue
        tempDirectory = "org.unifiedfontobject.normalizer.%d" % index
        subpathRenameDirectory(ufoPath, oldLayerDirectory, tempDirectory)
        fromTempMapping[tempDirectory] = newLayerDirectory
    for tempDirectory, newLayerDirectory in fromTempMapping.items():
        subpathRenameDirectory(ufoPath, tempDirectory, newLayerDirectory)
    # update layercontents.plist
    subpathWritePlist(newLayerMapping, ufoPath, "layercontents.plist")
    return newLayerMapping

def _test_normalizeGlyphsDirectoryNames(oldLayers, expectedLayers):
    import tempfile
    directory = tempfile.mkdtemp()
    for subDirectory in oldLayers.values():
        os.mkdir(os.path.join(directory, subDirectory))
    assert sorted(os.listdir(directory)) == sorted(oldLayers.values())
    subpathWritePlist(oldLayers, directory, "layercontents.plist")
    newLayers = normalizeGlyphsDirectoryNames(directory)
    listing = os.listdir(directory)
    listing.remove("layercontents.plist")
    assert sorted(listing) == sorted(newLayers.values())
    shutil.rmtree(directory)
    return newLayers == expectedLayers

# ------
# Glyphs
# ------

def normalizeUFO1And2GlyphsDirectory(ufoPath, modTimes):
    glyphMapping = normalizeGlyphNames(ufoPath, "glyphs")
    for fileName in sorted(glyphMapping.values()):
        location = subpathJoin("glyphs", fileName)
        if subpathNeedsRefresh(modTimes, ufoPath, location):
            normalizeGLIF(ufoPath, "glyphs", fileName)
            modTimes[location] = subpathGetModTime(ufoPath, "glyphs", fileName)

def normalizeGlyphsDirectory(ufoPath, layerDirectory, onlyModified=True):
    if subpathExists(ufoPath, layerDirectory, "layerinfo.plist"):
        layerInfo = subpathReadPlist(ufoPath, layerDirectory, "layerinfo.plist")
        layerLib = layerInfo.get("lib", {})
    else:
        layerLib = {}
    if onlyModified:
        modTimes = readModTimes(layerLib)
    else:
        modTimes = {}
    glyphMapping = normalizeGlyphNames(ufoPath, layerDirectory)
    for fileName in glyphMapping.values():
        if subpathNeedsRefresh(modTimes, ufoPath, layerDirectory, fileName):
            normalizeGLIF(ufoPath, layerDirectory, fileName)
            modTimes[location] = subpathGetModTime(ufoPath, layerDirectory, fileName)
    storeModTimes(layerLib, modTimes)
    normalizeLayerInfoPlist(ufoPath, layerDirectory)

def normalizeLayerInfoPlist(ufoPath, layerDirectory):
    # TO DO: normalize colors
    if subpathExists(ufoPath, layerDirectory, "layerinfo.plist"):
        _normalizePlistFile(ufoPath, layerDirectory, "layerinfo.plist")

def normalizeGlyphNames(ufoPath, layerDirectory):
    """
    non-standard file names
    -----------------------
    >>> oldNames = {
    ...     "A" : "a.glif",
    ...     "B" : "b.glif"
    ... }
    >>> expectedNames = {
    ...     "A" : "A_.glif",
    ...     "B" : "B_.glif"
    ... }
    >>> _test_normalizeGlyphNames(oldNames, expectedNames)
    True

    old file with same name as new file
    -----------------------------------
    >>> oldNames = {
    ...     "one" : "two.glif",
    ...     "two" : "three.glif"
    ... }
    >>> expectedNames = {
    ...     "one" : "one.glif",
    ...     "two" : "two.glif"
    ... }
    >>> _test_normalizeGlyphNames(oldNames, expectedNames)
    True
    """
    # INVALID DATA POSSIBILITY: no contents.plist
    # INVALID DATA POSSIBILITY: file for glyph name may not exist
    # INVALID DATA POSSIBILITY: file for glyph may not be stored in contents
    if not subpathExists(ufoPath, layerDirectory, "contents.plist"):
        return {}
    oldGlyphMapping = subpathReadPlist(ufoPath, layerDirectory, "contents.plist")
    newGlyphMapping = {}
    newFileNames = set()
    for glyphName in sorted(oldGlyphMapping.keys()):
        newFileName = userNameToFileName(unicode(glyphName), newFileNames, suffix=".glif")
        newFileNames.add(newFileName)
        newGlyphMapping[glyphName] = newFileName
    # don't do a direct rewrite in case an old file has
    # the same name as a new file.
    fromTempMapping = {}
    for index, (glyphName, newFileName) in enumerate(sorted(newGlyphMapping.items())):
        oldFileName = oldGlyphMapping[glyphName]
        if newFileName == oldFileName:
            continue
        tempFileName = "org.unifiedfontobject.normalizer.%d" % index
        subpathRenameFile(ufoPath, (layerDirectory, oldFileName), (layerDirectory, tempFileName))
        fromTempMapping[tempFileName] = newFileName
    for tempFileName, newFileName in fromTempMapping.items():
        subpathRenameFile(ufoPath, (layerDirectory, tempFileName), (layerDirectory, newFileName))
    # update contents.plist
    subpathWritePlist(newGlyphMapping, ufoPath, layerDirectory, "contents.plist")
    return newGlyphMapping

def _test_normalizeGlyphNames(oldGlyphMapping, expectedGlyphMapping):
    import tempfile
    directory = tempfile.mkdtemp()
    layerDirectory = "glyphs"
    fullLayerDirectory = subpathJoin(directory, layerDirectory)
    os.mkdir(fullLayerDirectory)
    for fileName in oldGlyphMapping.values():
        subpathWriteFile("", directory, layerDirectory, fileName)
    assert sorted(os.listdir(fullLayerDirectory)) == sorted(oldGlyphMapping.values())
    subpathWritePlist(oldGlyphMapping, directory, layerDirectory, "contents.plist")
    newGlyphMapping = normalizeGlyphNames(directory, layerDirectory)
    listing = os.listdir(fullLayerDirectory)
    listing.remove("contents.plist")
    assert sorted(listing) == sorted(newGlyphMapping.values())
    assert subpathReadPlist(directory, layerDirectory, "contents.plist") == newGlyphMapping
    shutil.rmtree(directory)
    return newGlyphMapping == expectedGlyphMapping

# ---------------
# Top-Level Files
# ---------------

# These are broken into separate, file specific
# functions for clarity and in case file specific
# normalization (such as filtering default values)
# needs to occur.

def _normalizePlistFile(modTimes, ufoPath, *subpath):
    if subpathNeedsRefresh(modTimes, ufoPath, *subpath):
        data = subpathReadPlist(ufoPath, *subpath)
        text = normalizePropertyList(data)
        subpathWriteFile(text, ufoPath, *subpath)
        modTimes[subpath[-1]] = subpathGetModTime(ufoPath, *subpath)

# metainfo.plist

def normalizeMetaInfoPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "metainfo.plist")

# fontinfo.plist

def normalizeFontInfoPlist(ufoPath, modTimes):
    # TO DO: normalize color strings
    _normalizePlistFile(modTimes, ufoPath, "fontinfo.plist")

# groups.plist

def normalizeGroupsPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "groups.plist")

# kerning.plist

def normalizeKerningPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "kerning.plist")

# layercontents.plist

def normalizeLayerContentsPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "layercontents.plist")

# lib.plist

def normalizeLibPlist(ufoPath):
    _normalizePlistFile({}, ufoPath, "lib.plist")

# -----------------
# XML Normalization
# -----------------

# Property List

def normalizePropertyList(data):
    writer = XMLWriter(isPropertyList=True)
    writer.propertyListObject(data)
    return writer.getText()

# GLIF

def normalizeGLIF(ufoPath, *subpath):
    """
    TO DO: need doctests
    The best way to test this is going to be have a GLIF
    that contains all of the element types. This can be
    round tripped and compared to make sure that the result
    matches the expectations. This GLIF doesn't need to
    contain a robust series of element variations as the
    testing of those will be handled by the element
    normalization functions.
    """
    # INVALID DATA POSSIBILITY: format version that can't be converted to int
    # read and parse
    glifPath = subpathJoin(ufoPath, *subpath)
    text = subpathReadFile(ufoPath, *subpath)
    tree = ET.fromstring(text)
    glifVersion = tree.attrib.get("format")
    if glifVersion is None:
        raise UFONormalizerError(u"Undefined GLIF format: %s" % glifPath)
    glifVersion = int(glifVersion)
    name = tree.attrib.get("name")
    # start the writer
    writer = XMLWriter()
    # grab the top-level elements
    advance = None
    unicodes = []
    note = None
    image = None
    guidelines = []
    anchors = []
    outline = None
    lib = None
    for element in tree:
        tag = element.tag
        if tag == "advance":
            advance = element
        elif tag == "unicode":
            unicodes.append(element)
        elif tag == "note":
            note = element
        elif tag == "image":
            image = element
        elif tag == "guideline":
            guidelines.append(element)
        elif tag == "anchor":
            anchors.append(element)
        elif tag == "outline":
            outline = element
        elif tag == "lib":
            lib = element
    # write the data
    writer.beginElement("glyph", attrs=dict(name=name, format=glifVersion))
    for uni in unicodes:
        _normalizeGlifUnicode(uni, writer)
    if advance is not None:
        _normalizeGlifAdvance(advance, writer)
    if glifVersion >= 2 and image is not None:
        _normalizeGlifImage(image, writer)
    if outline is not None:
        if glifVersion == 1:
            _normalizeGlifOutlineFormat1(outline, writer)
        else:
            _normalizeGlifOutlineFormat2(outline, writer)
    if glifVersion >= 2:
        for anchor in anchors:
            _normalizeGlifAnchor(anchor, writer)
    if glifVersion >= 2:
        for guideline in guidelines:
            _normalizeGlifGuideline(guideline, writer)
    if lib is not None:
        _normalizeGlifLib(lib, writer)
    if note is not None:
        _normalizeGlifNote(note, writer)
    writer.endElement("glyph")
    # write to the file
    text = writer.getText()
    subpathWriteFile(text, ufoPath, *subpath)

def _normalizeGlifUnicode(element, writer):
    """
    >>> element = ET.fromstring('<unicode />')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<unicode hex=""/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<unicode hexagon=""/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<unicode hex="0041"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="0041"/>'

    >>> element = ET.fromstring('<unicode hex="41"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="0041"/>'

    >>> element = ET.fromstring('<unicode hex="ea"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="00EA"/>'

    >>> element = ET.fromstring('<unicode hex="2Af"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="02AF"/>'

    >>> element = ET.fromstring('<unicode hex="xyz"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<unicode hex="0000fFfF"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="FFFF"/>'

    >>> element = ET.fromstring('<unicode hex="10000"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="10000"/>'

    >>> element = ET.fromstring('<unicode hex="abcde"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifUnicode(element, writer)
    >>> writer.getText()
    u'<unicode hex="ABCDE"/>'
    """
    v = element.attrib.get("hex")
    # INVALID DATA POSSIBILITY: no hex value
    if v:
    # INVALID DATA POSSIBILITY: invalid hex value
        try:
            d = int(v, 16)
            v = "%04X" % d
        except ValueError:
            return
    else:
        return
    writer.simpleElement("unicode", attrs=dict(hex=v))

def _normalizeGlifAdvance(element, writer):
    """
    >>> element = ET.fromstring('<advance />')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<advance width="0"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<advance height="0"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<advance width="0" height="0"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<advance bogus="450"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<advance width="325.0" bogus="450"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u'<advance width="325"/>'

    >>> element = ET.fromstring('<advance width="0" height="350.0"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u'<advance height="350"/>'

    >>> element = ET.fromstring('<advance width="200.98765432198765" height="0.0500" />')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u'<advance height="0.05" width="200.987654322"/>'

    >>> element = ET.fromstring('<advance width="2.000" height="-500"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u'<advance height="-500" width="2"/>'

    >>> element = ET.fromstring('<advance width="-0.0" height="-10.001"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAdvance(element, writer)
    >>> writer.getText()
    u'<advance height="-10.001"/>'
    """
    # INVALID DATA POSSIBILITY: value that can't be converted to float
    w = element.attrib.get("width", "0")
    w = float(w)
    h = element.attrib.get("height", "0")
    h = float(h)
    attrs = {}
    # filter out default value (0)
    if w:
        attrs["width"] = w
    if h:
        attrs["height"] = h
    if not attrs:
        return
    writer.simpleElement("advance", attrs=attrs)

def _normalizeGlifImage(element, writer):
    """
    TO DO: expand doctests

    >>> element = ET.fromstring('<image fileName="" xOffset="" yOffset="" color="" xScale="" xyScale="" yxScale="" yScale=""/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifImage(element, writer)
    >>> writer.getText()
    u'<image fileName="" xScale="" xyScale="" yxScale="" yScale="" xOffset="" yOffset="" color=""/>'

    >>> element = ET.fromstring('<image fileName="Sketch 1.png" xOffset="100" yOffset="200" xScale=".75" yScale=".75" color="1,0,0,.5" />')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifImage(element, writer)
    >>> writer.getText()
    u'<image fileName="Sketch 1.png" xScale=".75" yScale=".75" xOffset="100" yOffset="200" color="1,0,0,.5"/>'
    """
    # INVALID DATA POSSIBILITY: no file name defined
    attrs = dict(
        fileName=element.attrib["fileName"]
    )
    transformation = _normalizeGlifTransformation(element)
    attrs.update(transformation)
    color = element.attrib.get("color")
    if color is not None:
        attrs["color"] = _normalizeColorString(color)
    writer.simpleElement("image", attrs=attrs)

def _normalizeGlifAnchor(element, writer):
    """
    TO DO: expand doctests

    >>> element = ET.fromstring('<anchor x="0" y="0" name="" color="" identifier=""/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAnchor(element, writer)
    >>> writer.getText()
    u'<anchor name="" x="0" y="0" color="" identifier=""/>'

    >>> element = ET.fromstring('<anchor y="04.50" x="230" name="_above" color="1,0,0,.5" identifier="7B86ACED-F5D7-409E-A67B-AC3DA57B5DAC"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifAnchor(element, writer)
    >>> writer.getText()
    u'<anchor name="_above" x="230" y="4.5" color="1,0,0,.5" identifier="7B86ACED-F5D7-409E-A67B-AC3DA57B5DAC"/>'
    """
    # INVALID DATA POSSIBILITY: no x defined
    # INVALID DATA POSSIBILITY: no y defined
    # INVALID DATA POSSIBILITY: x or y that can't be converted to float
    attrs = dict(
        x=float(element.attrib["x"]),
        y=float(element.attrib["y"])
    )
    name = element.attrib.get("name")
    if name is not None:
        attrs["name"] = name
    color = element.attrib.get("color")
    if color is not None:
        attrs["color"] = _normalizeColorString(color)
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        attrs["identifier"] = identifier
    writer.simpleElement("anchor", attrs=attrs)

def _normalizeGlifGuideline(element, writer):
    """
    TO DO: expand doctests

    >>> element = ET.fromstring('<guideline x="0" y="0" angle="0" name="" color="" identifier=""/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifGuideline(element, writer)
    >>> writer.getText()
    u'<guideline name="" x="0" y="0" color="" identifier="" angle="0"/>'

    >>> element = ET.fromstring('<guideline x="670.325" y="-41" angle="360" name="accent height" color=".2,.3,.4,.5" identifier="#horizontal"/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifGuideline(element, writer)
    >>> writer.getText()
    u'<guideline name="accent height" x="670.325" y="-41" color=".2,.3,.4,.5" identifier="#horizontal" angle="360"/>'
    """
    # INVALID DATA POSSIBILITY: no x defined
    # INVALID DATA POSSIBILITY: no y defined
    # INVALID DATA POSSIBILITY: angle not defined following spec
    # INVALID DATA POSSIBILITY: x, y or angle that can't be converted to float
    attrs = dict(
        x=float(element.attrib["x"]),
        y=float(element.attrib["y"])
    )
    angle = element.attrib.get("angle")
    if angle is not None:
        attrs["angle"] = float(angle)
    name = element.attrib.get("name")
    if name is not None:
        attrs["name"] = name
    color = element.attrib.get("color")
    if color is not None:
        attrs["color"] = _normalizeColorString(color)
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        attrs["identifier"] = identifier
    writer.simpleElement("guideline", attrs=attrs)

def _normalizeGlifLib(element, writer):
    obj = _convertPlistElementToObject(element[0])
    if obj:
        writer.beginElement("lib")
        writer.propertyListObject(obj)
        writer.endElement("lib")

def _normalizeGlifNote(element, writer):
    r"""
    >>> element = ET.fromstring('<note></note>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifNote(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<note/>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifNote(element, writer)
    >>> writer.getText()
    u''

    >>> element = ET.fromstring('<note>Blah</note>')
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifNote(element, writer)
    >>> writer.getText()
    u'<note>\n\tBlah\n</note>'

    >>> element = ET.fromstring("<note>Don't forget to check the béziers!!</note>")
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifNote(element, writer)
    >>> writer.getText()
    u"<note>\n\tDon't forget to check the b\xe9ziers!!\n</note>"

    >>> element = ET.fromstring("<note>A quick brown fox jumps over the lazy dog.\nPříliš žluťoučký kůň úpěl ďábelské ódy.</note>")
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifNote(element, writer)
    >>> writer.getText()
    u'<note>\n\tA quick brown fox jumps over the lazy dog.\n\tP\u0159\xedli\u0161 \u017elu\u0165ou\u010dk\xfd k\u016f\u0148 \xfap\u011bl \u010f\xe1belsk\xe9 \xf3dy.\n</note>'
    """
    value = element.text
    if not value:
        return
    writer.beginElement("note")
    writer.text(value)
    writer.endElement("note")

def _normalizeGlifOutlineFormat1(element, writer):
    r"""
    >>> outline = '''
    ... <outline>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat1(element, writer)
    >>> writer.getText()
    u'<outline>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <contour>
    ...     </contour>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat1(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<contour>\n\t</contour>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <component base=""/>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat1(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<component base=""/>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <contour>
    ...         <point type="line" y="0" x="0"/>
    ...     </contour>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat1(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<contour>\n\t\t<point x="0" y="0" type="line"/>\n\t</contour>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <component base="C"/>
    ...     <contour>
    ...         <point type="line" y="0" x="0"/>
    ...     </contour>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat1(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<component base="C"/>\n\t<contour>\n\t\t<point x="0" y="0" type="line"/>\n\t</contour>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <contour>
    ...         <point y="250" x="150"/>
    ...         <point x="193" y="187"/>
    ...     </contour>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat1(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<contour>\n\t\t<point x="150" y="250"/>\n\t\t<point x="193" y="187"/>\n\t</contour>\n</outline>'

#     >>> outline = '''
#     ... <outline>
#     ...     <contour>
#     ...         <point y="250" x="150"/>
#     ...     </contour>
#     ... </outline>
#     ... '''
#     >>> element = ET.fromstring(outline)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifOutlineFormat1(element, writer)
#     >>> writer.getText()
#     u'<outline>\n\t<contour>\n\t\t<point x="150" y="250"/>\n\t</contour>\n</outline>'

#     >>> outline = '''
#     ... <outline>
#     ...     <contour>
#     ...         <point type="move" y="20" x="20"/>
#     ...     </contour>
#     ... </outline>
#     ... '''
#     >>> element = ET.fromstring(outline)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifOutlineFormat1(element, writer)
#     >>> writer.getText()
#     u'<outline>\n\t<contour>\n\t\t<point x="20" y="20" type="move"/>\n\t</contour>\n</outline>'
    """
    writer.beginElement("outline")
    anchors = []
    for subElement in element:
        tag = subElement.tag
        if tag == "contour":
            anchor = _normalizeGlifContourFormat1(subElement, writer)
            if anchor is not None:
                anchors.append(anchor)
        elif tag == "component":
            _normalizeGlifComponentFormat1(subElement, writer)
    for anchor in anchors:
        attrs = dict(
            type="move",
            x=anchor["x"],
            y=anchor["y"]
        )
        writer.simpleElement("point", attrs=attrs)
    writer.endElement("outline")

def _normalizeGlifContourFormat1(element, writer):
    r"""
    >>> contour = '''
    ... <contour>
    ... </contour>
    ... '''
    >>> element = ET.fromstring(contour)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifContourFormat1(element, writer)
    >>> writer.getText()
    u'<contour>\n</contour>'

    >>> contour = '''
    ... <contour>
    ...     <point type="line" y="0" x="0"/>
    ... </contour>
    ... '''
    >>> element = ET.fromstring(contour)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifContourFormat1(element, writer)
    >>> writer.getText()
    u'<contour>\n\t<point x="0" y="0" type="line"/>\n</contour>'

    >>> contour = '''
    ... <contour>
    ...     <point y="250" x="150"/>
    ...     <point x="193" y="187"/>
    ... </contour>
    ... '''
    >>> element = ET.fromstring(contour)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifContourFormat1(element, writer)
    >>> writer.getText()
    u'<contour>\n\t<point x="150" y="250"/>\n\t<point x="193" y="187"/>\n</contour>'

    >>> contour = '''
    ... <contour>
    ...     <point x="250" smooth="yes" y="650" type="curve" name="top"/>
    ... </contour>
    ... '''
    >>> element = ET.fromstring(contour)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifContourFormat1(element, writer)
    >>> writer.getText()
    u'<contour>\n\t<point name="top" x="250" y="650" type="curve" smooth="yes"/>\n</contour>'

#     >>> contour = '''
#     ... <contour>
#     ...     <point x="250" y="650"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat1(element, writer)
#     >>> writer.getText()
#     u''

#     >>> contour = '''
#     ... <contour>
#     ...     <point x="250" y="650" type="move"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat1(element, writer)
#     >>> writer.getText()
#     u''
    """
    # INVALID DATA POSSIBILITY: unknown child element
    # INVALID DATA POSSIBILITY: unknown point type
    points = []
    for subElement in element:
        tag = subElement.tag
        if tag != "point":
            continue
        attrs = _normalizeGlifPointAttributesFormat1(subElement)
        points.append(attrs)
    # anchor
    if len(points) == 1 and points[0]["type"] == "move":
        return points[0]
    # contour
    writer.beginElement("contour")
    for point in points:
        writer.simpleElement("point", attrs=point)
    writer.endElement("contour")

def _normalizeGlifPointAttributesFormat1(element):
    """
    >>> point = '''<point x="210" y="476"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat1(element)
    {'y': 476.0, 'x': 210.0}

    >>> point = '''<point x="134" y="187" type="curve" smooth="yes" name="corner"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat1(element)
    {'y': 187.0, 'x': 134.0, 'type': 'curve', 'smooth': 'yes', 'name': 'corner'}

    >>> point = '''<point x="134.45" y="187.78" type="offcurve" smooth="no" name="corner"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat1(element)
    {'y': 187.78, 'x': 134.45, 'name': 'corner'}

    >>> point = '''<point x="310" y="475" type="move"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat1(element)
    {'y': 475.0, 'x': 310.0, 'type': 'move'}
    """
    # INVALID DATA POSSIBILITY: no x defined
    # INVALID DATA POSSIBILITY: no y defined
    # INVALID DATA POSSIBILITY: x or y that can't be converted to float
    # INVALID DATA POSSIBILITY: duplicate attributes
    attrs = dict(
        x=float(element.attrib["x"]),
        y=float(element.attrib["y"])
    )
    typ = element.attrib.get("type", "offcurve")
    if typ != "offcurve":
        attrs["type"] = typ
        smooth = element.attrib.get("smooth", "no")
        if smooth == "yes":
            attrs["smooth"] = "yes"
    name = element.attrib.get("name")
    if name is not None:
        attrs["name"] = name
    return attrs

def _normalizeGlifComponentFormat1(element, writer):
    """
    >>> component = '''<component base="A"/>'''
    >>> element = ET.fromstring(component)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifComponentFormat1(element, writer)
    >>> writer.getText()
    u'<component base="A"/>'

    >>> component = '''<component xOffset="260" base="acutecmb.cap"/>'''
    >>> element = ET.fromstring(component)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifComponentFormat1(element, writer)
    >>> writer.getText()
    u'<component base="acutecmb.cap" xOffset="260"/>'
    """
    # INVALID DATA POSSIBILITY: no base defined
    # INVALID DATA POSSIBILITY: unknown child element
    attrs = _normalizeGlifComponentAttributesFormat1(element)
    writer.simpleElement("component", attrs=attrs)

def _normalizeGlifComponentAttributesFormat1(element):
    """
    >>> component = '''<component base="A"/>'''
    >>> element = ET.fromstring(component)
    >>> _normalizeGlifComponentAttributesFormat1(element)
    {'base': 'A'}

    >>> component = '''<component xOffset="105" xScale=".75" yScale=".85" yOffset="200" base="B" xyScale="2" yxScale="0"/>'''
    >>> element = ET.fromstring(component)
    >>> _normalizeGlifComponentAttributesFormat1(element)
    {'xScale': '.75', 'base': 'B', 'xOffset': '105', 'yScale': '.85', 'yxScale': '0', 'xyScale': '2', 'yOffset': '200'}
    """
    # INVALID DATA POSSIBILITY: no base defined
    # INVALID DATA POSSIBILITY: duplicate attributes
    attrs = dict(
        base=element.attrib["base"]
    )
    transformation = _normalizeGlifTransformation(element)
    attrs.update(transformation)
    return attrs

def _normalizeGlifOutlineFormat2(element, writer):
    r"""
    >>> outline = '''
    ... <outline>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat2(element, writer)
    >>> writer.getText()
    u'<outline>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <contour>
    ...     </contour>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat2(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<contour>\n\t</contour>\n</outline>'

    >>> outline = '''
    ... <outline>
    ...     <component base=""/>
    ... </outline>
    ... '''
    >>> element = ET.fromstring(outline)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifOutlineFormat2(element, writer)
    >>> writer.getText()
    u'<outline>\n\t<component base=""/>\n</outline>'
    """
    writer.beginElement("outline")
    for subElement in element:
        tag = subElement.tag
        if tag == "contour":
            _normalizeGlifContourFormat2(subElement, writer)
        elif tag == "component":
            _normalizeGlifComponentFormat2(subElement, writer)
    writer.endElement("outline")

def _normalizeGlifContourFormat2(element, writer):
    r"""
    >>> contour = '''
    ... <contour>
    ... </contour>
    ... '''
    >>> element = ET.fromstring(contour)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifContourFormat2(element, writer)
    >>> writer.getText()
    u'<contour>\n</contour>'

#     >>> contour = '''
#     ... <contour>
#     ...     <point type="line" y="0" x="0" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat2(element, writer)
#     >>> writer.getText()
#     u'<contour>\n\t<point x="0" y="0" type="line" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73"/>\n</contour>'

#     >>> contour = '''
#     ... <contour>
#     ...     <point y="250" x="150" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73"/>
#     ...     <point x="193" y="187"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat2(element, writer)
#     >>> writer.getText()
#     u'<contour>\n\t<point x="150" y="250" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73"/>\n\t<point x="193" y="187"/>\n</contour>'

#     >>> contour = '''
#     ... <contour>
#     ...     <point x="250" smooth="yes" y="650" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73" type="curve" name="top"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat2(element, writer)
#     >>> writer.getText()
#     u'<contour>\n\t<point name="top" x="250" y="650" type="curve" smooth="yes" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73"/>\n</contour>'

#     >>> contour = '''
#     ... <contour>
#     ...     <point x="250" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73" y="650"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat2(element, writer)
#     >>> writer.getText()
#     u''

#     >>> contour = '''
#     ... <contour>
#     ...     <point x="250" y="650" type="move" identifier="CDC4111B-A72D-49CD-84FC-5883AE2DFA73"/>
#     ... </contour>
#     ... '''
#     >>> element = ET.fromstring(contour)
#     >>> writer = XMLWriter(declaration=None)
#     >>> _normalizeGlifContourFormat2(element, writer)
#     >>> writer.getText()
#     u''
    """
    # INVALID DATA POSSIBILITY: unknown child element
    # INVALID DATA POSSIBILITY: unknown point type
    attrs = {}
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        attrs["identifier"] = identifier
    writer.beginElement("contour", attrs=attrs)
    for subElement in element:
        tag = subElement.tag
        if tag != "point":
            continue
        attrs = _normalizeGlifPointAttributesFormat2(subElement)
        points.append(attrs)
        writer.simpleElement("point", attrs=attrs)
    writer.endElement("contour")

def _normalizeGlifPointAttributesFormat2(element):
    """
    >>> point = '''<point identifier="F3E3C752-B7B3-423D-9519-119C3A2D09A0" x="210" y="476"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat2(element)
    {'y': 476.0, 'x': 210.0, 'identifier': 'F3E3C752-B7B3-423D-9519-119C3A2D09A0'}

    >>> point = '''<point x="134" y="187" type="curve" identifier="F3E3C752-B7B3-423D-9519-119C3A2D09A0" smooth="yes" name="corner"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat2(element)
    {'name': 'corner', 'smooth': 'yes', 'y': 187.0, 'x': 134.0, 'identifier': 'F3E3C752-B7B3-423D-9519-119C3A2D09A0', 'type': 'curve'}

    >>> point = '''<point x="134.45" y="187.78" type="offcurve" smooth="no" name="corner" identifier="F3E3C752-B7B3-423D-9519-119C3A2D09A0"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat2(element)
    {'y': 187.78, 'x': 134.45, 'identifier': 'F3E3C752-B7B3-423D-9519-119C3A2D09A0', 'name': 'corner'}

    >>> point = '''<point x="310" y="475" identifier="F3E3C752-B7B3-423D-9519-119C3A2D09A0" type="move"/>'''
    >>> element = ET.fromstring(point)
    >>> _normalizeGlifPointAttributesFormat2(element)
    {'y': 475.0, 'x': 310.0, 'identifier': 'F3E3C752-B7B3-423D-9519-119C3A2D09A0', 'type': 'move'}
    """
    attrs = _normalizeGlifPointAttributesFormat1(element)
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        attrs["identifier"] = identifier
    return attrs

def _normalizeGlifComponentFormat2(element, writer):
    """
    >>> component = '''<component base="A"/>'''
    >>> element = ET.fromstring(component)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifComponentFormat2(element, writer)
    >>> writer.getText()
    u'<component base="A"/>'

    >>> component = '''<component xOffset="260" base="acutecmb.cap"/>'''
    >>> element = ET.fromstring(component)
    >>> writer = XMLWriter(declaration=None)
    >>> _normalizeGlifComponentFormat2(element, writer)
    >>> writer.getText()
    u'<component base="acutecmb.cap" xOffset="260"/>'
    """
    attrs = _normalizeGlifComponentAttributesFormat2(element)
    writer.simpleElement("component", attrs=attrs)

def _normalizeGlifComponentAttributesFormat2(element):
    """
    >>> component = '''<component identifier="F8B150BD-3B11-47A9-BBD2-B2C4A721D734" base="A"/>'''
    >>> element = ET.fromstring(component)
    >>> _normalizeGlifComponentAttributesFormat2(element)
    {'base': 'A', 'identifier': 'F8B150BD-3B11-47A9-BBD2-B2C4A721D734'}

    >>> component = '''<component identifier="F8B150BD-3B11-47A9-BBD2-B2C4A721D734" xOffset="105" xScale=".75" yScale=".85" yOffset="200" base="B" xyScale="2" yxScale="0"/>'''
    >>> element = ET.fromstring(component)
    >>> _normalizeGlifComponentAttributesFormat2(element)
    {'xScale': '.75', 'base': 'B', 'xOffset': '105', 'yScale': '.85', 'yxScale': '0', 'identifier': 'F8B150BD-3B11-47A9-BBD2-B2C4A721D734', 'xyScale': '2', 'yOffset': '200'}
    """
    attrs = _normalizeGlifComponentAttributesFormat1(element)
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        attrs["identifier"] = identifier
    return attrs

_glifDefaultTransformation = dict(
    xScale=1,
    xyScale=0,
    yxScale=0,
    yScale=1,
    xOffset=0,
    yOffset=0
)

def _normalizeGlifTransformation(element):
    """
    >>> element = ET.fromstring('<component base="B" xScale="1" xyScale="0" yxScale="0" yScale="1" xOffset="0" yOffset="0"/>')
    >>> _normalizeGlifTransformation(element)
    {'yScale': '1', 'yxScale': '0', 'yOffset': '0', 'xyScale': '0', 'xScale': '1', 'xOffset': '0'}

    >>> element = ET.fromstring('<component identifier="F8B150BD-3B11-47A9-BBD2-B2C4A721D734" xOffset="105" xScale=".75" yScale=".85" yOffset="200" base="B" xyScale="2" yxScale="0"/>')
    >>> _normalizeGlifTransformation(element)
    {'yScale': '.85', 'yxScale': '0', 'yOffset': '200', 'xyScale': '2', 'xScale': '.75', 'xOffset': '105'}

    >>> element = ET.fromstring('<image fileName="Sketch 1.png" xOffset="100" yOffset="200" xScale=".75" yScale=".75" color="1,0,0,.5" />')
    >>> _normalizeGlifTransformation(element)
    {'xScale': '.75', 'yOffset': '200', 'xOffset': '100', 'yScale': '.75'}
    """
    attrs = {}
    for attr, default in _glifDefaultTransformation.items():
        value = element.attrib.get(attr, default)
        if value != default:
            attrs[attr] = value
    return attrs

def _normalizeColorString(value):
    """
    TO DO: need doctests
    """
    # TO DO: implement this
    # INVALID DATA POSSIBILITY: bad color string
    return value

def _convertPlistElementToObject(element):
    """
    TO DO: need doctests
    """
    # INVALID DATA POSSIBILITY: invalid value string
    obj = None
    tag = element.tag
    if tag == "array":
        obj = []
        for subElement in element:
            obj.append(_convertPlistElementToObject(subElement))
    elif tag == "dict":
        obj = {}
        key = None
        for subElement in element:
            if subElement.tag == "key":
                key = subElement.text
            else:
                obj[key] = _convertPlistElementToObject(subElement)
    elif tag == "string":
        return element.text
    elif tag == "data":
        # TO DO: implement this
        # needs to convert to plistlib.Data
        raise NotImplementedError
    elif tag == "date":
        # TO DO: implement this
        # needs to convert to datetime.datetime
        raise NotImplementedError
    elif tag == "true":
        return True
    elif tag == "false":
        return False
    elif tag == "real":
        return float(element.text)
    elif tag == "integer":
        return int(element.text)
    return obj

# XML Writer

xmlDeclaration = u"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
plistDocType = "<!DOCTYPE plist PUBLIC \"-//Apple Computer//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">"
xmlTextMaxLineLength = 70
xmlIndent = u"\t"
xmlLineBreak = u"\n"
xmlAttributeOrder = u"""
name
base
format
fileName
base
x
y
xScale
xyScale
yxScale
yScale
xOffset
yOffset
type
smooth
color
identifier
""".strip().splitlines()
d = {}
for index, attr in enumerate(xmlAttributeOrder):
    d[attr] = index
xmlAttributeOrder = d

class XMLWriter(object):

    def __init__(self, isPropertyList=False, declaration=xmlDeclaration):
        self._lines = []
        if declaration:
            self._lines.append(declaration)
        if isPropertyList:
            self._lines.append(plistDocType)
        self._indentLevel = 0
        self._stack = []

    # text retrieval

    def getText(self):
        assert not self._stack
        return xmlLineBreak.join(self._lines)

    # writing

    def raw(self, line):
        if self._indentLevel:
            i = xmlIndent * self._indentLevel
            line = i + line
        self._lines.append(line)

    def data(self, text):
        line = "<![CDATA[%s]]>" % text
        self.raw(line)

    def text(self, text):
        text = text.strip()
        text = xmlEscapeText(text)
        paragraphs = []
        for paragraph in text.splitlines():
            if not paragraph:
                paragraphs.append("")
            else:
                paragraph = textwrap.wrap(paragraph,
                    width=xmlTextMaxLineLength,
                    expand_tabs=False,
                    replace_whitespace=False,
                    drop_whitespace=False,
                    break_long_words=False,
                    break_on_hyphens=False
                )
                paragraphs.extend(paragraph)
        for line in paragraphs:
            self.raw(line)

    def simpleElement(self, tag, attrs={}, value=None):
        if attrs:
            attrs = self.attributesToString(attrs)
            line = "<%s %s" % (tag, attrs)
        else:
            line = "<%s" % tag
        if value is not None:
            line = "%s>%s</%s>" % (line, value, tag)
        else:
            line = "%s/>" % line
        self.raw(line)

    def beginElement(self, tag, attrs={}):
        if attrs:
            attrs = self.attributesToString(attrs)
            line = "<%s %s>" % (tag, attrs)
        else:
            line = "<%s>" % tag
        self.raw(line)
        self._stack.append(tag)
        self._indentLevel += 1

    def endElement(self, tag):
        assert self._stack
        assert self._stack[-1] == tag
        del self._stack[-1]
        self._indentLevel -= 1
        line = "</%s>" % (tag)
        self.raw(line)

    # property list

    def propertyListObject(self, data):
        """
        Array:

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject([])
        >>> writer.getText()
        u'<array>\\n</array>'

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(["a"])
        >>> writer.getText()
        u'<array>\\n\\t<string>a</string>\\n</array>'

        Dict:

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject({})
        >>> writer.getText()
        u'<dict>\\n</dict>'

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject({"a" : "b"})
        >>> writer.getText()
        u'<dict>\\n\\t<key>a</key>\\n\\t<string>b</string>\\n</dict>'

        String:

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject("a")
        >>> writer.getText()
        u'<string>a</string>'

        Boolean:

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(True)
        >>> writer.getText()
        u'<true/>'

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(False)
        >>> writer.getText()
        u'<false/>'

        Float:

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(1.1)
        >>> writer.getText()
        u'<real>1.1</real>'

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(-1.1)
        >>> writer.getText()
        u'<real>-1.1</real>'

        Integer:

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(1)
        >>> writer.getText()
        u'<integer>1</integer>'

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(-1)
        >>> writer.getText()
        u'<integer>-1</integer>'

        >>> writer = XMLWriter(declaration=None)
        >>> writer.propertyListObject(0)
        >>> writer.getText()
        u'<integer>0</integer>'

        Date:
        # TO DO: need doctests

        Data:

        >>> writer = XMLWriter(declaration=None)
        >>> data = plistlib.Data("abc")
        >>> writer.propertyListObject(data)
        >>> writer.getText()
        u'<data>\\n\\tYWJj\\n</data>'
        """
        if data is None:
            return
        if isinstance(data, (list, tuple)):
            self._plistArray(data)
        elif isinstance(data, dict):
            self._plistDict(data)
        elif isinstance(data, basestring):
            self._plistString(data)
        elif isinstance(data, bool):
            self._plistBoolean(data)
        elif isinstance(data, (int, long)):
            self._plistInt(data)
        elif isinstance(data, float):
            self._plistFloat(data)
        elif isinstance(data, plistlib.Data):
            self._plistData(data)
        elif isinstance(data, datetime.datetime):
            self._plistDate(data)
        else:
            raise UFONormalizerError("Unknown data type in property list: %s" % repr(type(data)))

    def _plistArray(self, data):
        self.beginElement("array")
        for value in data:
            self.propertyListObject(value)
        self.endElement("array")

    def _plistDict(self, data):
        self.beginElement("dict")
        for key, value in sorted(data.items()):
            self.simpleElement("key", value=key)
            self.propertyListObject(value)
        self.endElement("dict")

    def _plistString(self, data):
        self.simpleElement("string", value=data)

    def _plistBoolean(self, data):
        if data:
            self.simpleElement("true")
        else:
            self.simpleElement("false")

    def _plistFloat(self, data):
        data = xmlConvertFloat(data)
        self.simpleElement("real", value=data)

    def _plistInt(self, data):
        data = xmlConvertInt(data)
        self.simpleElement("integer", value=data)

    def _plistDate(self, data):
        # TO DO: implement this. refer to plistlib.py.
        raise NotImplementedError

    def _plistData(self, data):
        self.beginElement("data")
        data = data.asBase64(maxlinelength=xmlTextMaxLineLength)
        for line in data.splitlines():
            self.raw(line)
        self.endElement("data")

    # support

    def attributesToString(self, attrs):
        """
        TO DO: need doctests
        """
        sorter = [
            (xmlAttributeOrder.get(attr, 100), attr, value) for (attr, value) in attrs.items()
        ]
        formatted = []
        for index, attr, value in sorted(sorter):
            attr = xmlEscapeAttribute(attr)
            value = xmlConvertValue(value)
            pair = u"%s=\"%s\"" % (attr, value)
            formatted.append(pair)
        return u" ".join(formatted)


def xmlEscapeText(text):
    """
    TO DO: need doctests
    """
    text = text.replace(u"&", u"&amp;")
    text = text.replace(u"<", u"&lt;")
    text = text.replace(u">", u"&gt;")
    return text

def xmlEscapeAttribute(text):
    """
    TO DO: need doctests
    """
    text = xmlEscapeText(text)
    text = text.replace(u"\"", u"&quot;")
    return text

def xmlConvertValue(value):
    """
    TO DO: need doctests
    """
    if isinstance(value, float):
        return xmlConvertFloat(value)
    elif isinstance(value, int):
        return xmlConvertInt(value)
    value = xmlEscapeText(value)
    return value

def xmlConvertFloat(value):
    """
    >>> xmlConvertFloat(1.0)
    '1'
    >>> xmlConvertFloat(1.01)
    '1.01'
    >>> xmlConvertFloat(1.0000000001)
    '1.0000000001'
    >>> xmlConvertFloat(1.00000000001)
    '1'
    >>> xmlConvertFloat(1.00000000009)
    '1.0000000001'
    """
    value = "%.10f" % value
    value = value.rstrip("0")
    if value[-1] == ".":
        return xmlConvertInt(int(float(value)))
    return value

def xmlConvertInt(value):
    """
    TO DO: need doctests
    """
    return str(value)

# ---------------
# Path Operations
# ---------------

def duplicateUFO(inPath, outPath):
    """
    Duplicate an entire UFO.
    """
    if os.path.exists(outPath):
        shutil.rmtree(outPath)
    shutil.copytree(inPath, outPath)

def subpathJoin(ufoPath, *subpath):
    """
    Join path parts.
    """
    if not isinstance(subpath, basestring):
        subpath = os.path.join(*subpath)
    return os.path.join(ufoPath, subpath)

def subpathExists(ufoPath, *subpath):
    """
    Get a boolean indicating if a path exists.
    """
    path = subpathJoin(ufoPath, *subpath)
    return os.path.exists(path)

# read

def subpathReadFile(ufoPath, *subpath):
    """
    Read the contents of a file.
    """
    path = subpathJoin(ufoPath, *subpath)
    f = open(path, "rb")
    text = f.read()
    f.close()
    return text

def subpathReadPlist(ufoPath, *subpath):
    """
    Read the contents of a property list
    and convert it into a Python object.
    """
    text = subpathReadFile(ufoPath, *subpath)
    return plistlib.readPlistFromString(text)

# write

def subpathWriteFile(data, ufoPath, *subpath):
    """
    Write data to a file.

    This will only modify the file if the
    file contains data that is different
    from the new data.
    """
    path = subpathJoin(ufoPath, *subpath)
    if subpathExists(ufoPath, *subpath):
        existing = subpathReadFile(ufoPath, *subpath)
    else:
        existing = None
    if data != existing:
        f = open(path, "wb")
        f.write(data)
        f.close()

def subpathWritePlist(data, ufoPath, *subpath):
    """
    Write a Python object to a property list.
    THIS DOES NOT WRITE NORMALIZED OUTPUT.

    This will only modify the file if the
    file contains data that is different
    from the new data.
    """
    data = plistlib.writePlistToString(data)
    subpathWriteFile(data, ufoPath, *subpath)

# rename

def subpathRenameFile(ufoPath, fromSubpath, toSubpath):
    """
    Rename a file.
    """
    if isinstance(fromSubpath, basestring):
        fromSubpath = [fromSubpath]
    if isinstance(toSubpath, basestring):
        toSubpath = [toSubpath]
    inPath = subpathJoin(ufoPath, *fromSubpath)
    outPath = subpathJoin(ufoPath, *toSubpath)
    os.rename(inPath, outPath)

def subpathRenameDirectory(ufoPath, fromSubpath, toSubpath):
    """
    Rename a directory.
    """
    if isinstance(fromSubpath, basestring):
        fromSubpath = [fromSubpath]
    if isinstance(toSubpath, basestring):
        toSubpath = [toSubpath]
    inPath = subpathJoin(ufoPath, *fromSubpath)
    outPath = subpathJoin(ufoPath, *toSubpath)
    shutil.move(inPath, outPath)

# mod times

def subpathGetModTime(ufoPath, *subpath):
    """
    Get the modification time for a file.
    """
    path = subpathJoin(ufoPath, *subpath)
    return os.path.getmtime(path)

def subpathNeedsRefresh(modTimes, ufoPath, *subPath):
    """
    Determine if a file needs to be refreshed.
    """
    previous = modTimes.get(subPath[-1])
    if previous is None:
        return True
    latest = subpathGetModTime(ufoPath, *subpath)
    return latest == previous

# ---------------
# Store Mod Times
# ---------------

def storeModTimes(lib, modTimes):
    """
    Write the file mod times to the lib.
    """
    lines = [
        "version: %s" % __version__
    ]
    for fileName, modTime in sorted(modTimes.items()):
        line = "%.1f %s" % (modTime, fileName)
        lines.append(line)
    text = "\n".join(lines)
    lib[modTimeLibKey] = text

def readModTimes(lib):
    """
    Read the file mod times from the lib.
    """
    # TO DO: a version mismatch causing a complete
    # renomalization of existing files sucks. but,
    # I haven't been able to come up with a better
    # solution. maybe we could keep track of what
    # would need new normalization from version to
    # version and only trigger it as needed. most
    # new versions aren't going to require a complete
    # rerun of everything.
    text = lib.get(modTimeLibKey)
    if not text:
        return {}
    lines = text.splitlines()
    version = lines.pop(0).split(":")[-1].strip()
    if version != __version__:
        return {}
    modTimes = {}
    for line in lines:
        modTime, fileName = line.split(" ", 1)
        modTime = float(modTime)
        modTimes[fileName] = modTime
    return text


# ----------------------
# User Name to File Name
# ----------------------
#
# This was taken directly from the UFO 3 specification.

illegalCharacters = "\" * + / : < > ? [ \ ] | \0".split(" ")
illegalCharacters += [chr(i) for i in range(1, 32)]
illegalCharacters += [chr(0x7F)]
reservedFileNames = "CON PRN AUX CLOCK$ NUL A:-Z: COM1".lower().split(" ")
reservedFileNames += "LPT1 LPT2 LPT3 COM2 COM3 COM4".lower().split(" ")
maxFileNameLength = 255

def userNameToFileName(userName, existing=[], prefix="", suffix=""):
    """
    existing should be a case-insensitive list
    of all existing file names.

    >>> userNameToFileName(u"a")
    u'a'
    >>> userNameToFileName(u"A")
    u'A_'
    >>> userNameToFileName(u"AE")
    u'A_E_'
    >>> userNameToFileName(u"Ae")
    u'A_e'
    >>> userNameToFileName(u"ae")
    u'ae'
    >>> userNameToFileName(u"aE")
    u'aE_'
    >>> userNameToFileName(u"a.alt")
    u'a.alt'
    >>> userNameToFileName(u"A.alt")
    u'A_.alt'
    >>> userNameToFileName(u"A.Alt")
    u'A_.A_lt'
    >>> userNameToFileName(u"A.aLt")
    u'A_.aL_t'
    >>> userNameToFileName(u"A.alT")
    u'A_.alT_'
    >>> userNameToFileName(u"T_H")
    u'T__H_'
    >>> userNameToFileName(u"T_h")
    u'T__h'
    >>> userNameToFileName(u"t_h")
    u't_h'
    >>> userNameToFileName(u"F_F_I")
    u'F__F__I_'
    >>> userNameToFileName(u"f_f_i")
    u'f_f_i'
    >>> userNameToFileName(u"Aacute_V.swash")
    u'A_acute_V_.swash'
    >>> userNameToFileName(u".notdef")
    u'_notdef'
    >>> userNameToFileName(u"con")
    u'_con'
    >>> userNameToFileName(u"CON")
    u'C_O_N_'
    >>> userNameToFileName(u"con.alt")
    u'_con.alt'
    >>> userNameToFileName(u"alt.con")
    u'alt._con'
    """
    # the incoming name must be a unicode string
    assert isinstance(userName, unicode), "The value for userName must be a unicode string."
    # establish the prefix and suffix lengths
    prefixLength = len(prefix)
    suffixLength = len(suffix)
    # replace an initial period with an _
    # if no prefix is to be added
    if not prefix and userName[0] == ".":
        userName = "_" + userName[1:]
    # filter the user name
    filteredUserName = []
    for character in userName:
        # replace illegal characters with _
        if character in illegalCharacters:
            character = "_"
        # add _ to all non-lower characters
        elif character != character.lower():
            character += "_"
        filteredUserName.append(character)
    userName = "".join(filteredUserName)
    # clip to 255
    sliceLength = maxFileNameLength - prefixLength - suffixLength
    userName = userName[:sliceLength]
    # test for illegal files names
    parts = []
    for part in userName.split("."):
        if part.lower() in reservedFileNames:
            part = "_" + part
        parts.append(part)
    userName = ".".join(parts)
    # test for clash
    fullName = prefix + userName + suffix
    if fullName.lower() in existing:
        fullName = handleClash1(userName, existing, prefix, suffix)
    # finished
    return fullName

def handleClash1(userName, existing=[], prefix="", suffix=""):
    """
    existing should be a case-insensitive list
    of all existing file names.

    >>> prefix = ("0" * 5) + "."
    >>> suffix = "." + ("0" * 10)
    >>> existing = ["a" * 5]

    >>> e = list(existing)
    >>> handleClash1(userName="A" * 5, existing=e,
    ...     prefix=prefix, suffix=suffix)
    '00000.AAAAA000000000000001.0000000000'

    >>> e = list(existing)
    >>> e.append(prefix + "aaaaa" + "1".zfill(15) + suffix)
    >>> handleClash1(userName="A" * 5, existing=e,
    ...     prefix=prefix, suffix=suffix)
    '00000.AAAAA000000000000002.0000000000'

    >>> e = list(existing)
    >>> e.append(prefix + "AAAAA" + "2".zfill(15) + suffix)
    >>> handleClash1(userName="A" * 5, existing=e,
    ...     prefix=prefix, suffix=suffix)
    '00000.AAAAA000000000000001.0000000000'
    """
    # if the prefix length + user name length + suffix length + 15 is at
    # or past the maximum length, silce 15 characters off of the user name
    prefixLength = len(prefix)
    suffixLength = len(suffix)
    if prefixLength + len(userName) + suffixLength + 15 > maxFileNameLength:
        l = (prefixLength + len(userName) + suffixLength + 15)
        sliceLength = maxFileNameLength - l
        userName = userName[:sliceLength]
    finalName = None
    # try to add numbers to create a unique name
    counter = 1
    while finalName is None:
        name = userName + str(counter).zfill(15)
        fullName = prefix + name + suffix
        if fullName.lower() not in existing:
            finalName = fullName
            break
        else:
            counter += 1
        if counter >= 999999999999999:
            break
    # if there is a clash, go to the next fallback
    if finalName is None:
        finalName = handleClash2(existing, prefix, suffix)
    # finished
    return finalName

def handleClash2(existing=[], prefix="", suffix=""):
    """
    existing should be a case-insensitive list
    of all existing file names.

    >>> prefix = ("0" * 5) + "."
    >>> suffix = "." + ("0" * 10)
    >>> existing = [prefix + str(i) + suffix for i in range(100)]

    >>> e = list(existing)
    >>> handleClash2(existing=e, prefix=prefix, suffix=suffix)
    '00000.100.0000000000'

    >>> e = list(existing)
    >>> e.remove(prefix + "1" + suffix)
    >>> handleClash2(existing=e, prefix=prefix, suffix=suffix)
    '00000.1.0000000000'

    >>> e = list(existing)
    >>> e.remove(prefix + "2" + suffix)
    >>> handleClash2(existing=e, prefix=prefix, suffix=suffix)
    '00000.2.0000000000'
    """
    # calculate the longest possible string
    maxLength = maxFileNameLength - len(prefix) - len(suffix)
    maxValue = int("9" * maxLength)
    # try to find a number
    finalName = None
    counter = 1
    while finalName is None:
        fullName = prefix + str(counter) + suffix
        if fullName.lower() not in existing:
            finalName = fullName
            break
        else:
            counter += 1
        if counter >= maxValue:
            break
    # raise an error if nothing has been found
    if finalName is None:
        raise NameTranslationError("No unique name could be found.")
    # finished
    return finalName


# -------
# Testing
# -------

if __name__ == "__main__":
    # doctests
    import doctest
    doctest.testmod()

    # test file searching
    import glob

    paths = []
    d = os.path.dirname(__file__)
    pattern = os.path.join(d, "test", "*.ufo")
    for inPath in glob.glob(pattern):
        if inPath.endswith("-n.ufo"):
            continue
        outPath = os.path.splitext(inPath)[0] + "-n.ufo"
        if os.path.exists(outPath):
            shutil.rmtree(outPath)
        paths.append((inPath, outPath))

    if paths:

        # profile test
        import cProfile

        inPath, outPath = paths[0]
        shutil.copytree(inPath, outPath)

        def runProfile():
            normalizeUFO(outPath)

        cProfile.run("runProfile()", sort="tottime")
        shutil.rmtree(outPath)

        # general test
        import time

        for inPath, outPath in paths:
            shutil.copytree(inPath, outPath)
            s = time.time()
            normalizeUFO(outPath)
            t = time.time() - s
            print os.path.basename(inPath) + ":", t, "seconds"
