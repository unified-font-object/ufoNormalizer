import os
import shutil
from xml.etree import cElementTree as ET
import plistlib
import textwrap
import datetime


"""
- once this is working, make it faster by storing mod times
  for each file in lib.plist + layerinfo.plist.
- force any PLIST data elements to proper base64 formatting.
- possibly add a -strict option that will remove unknown
  directories/files/elements/attributes and fix glaring errors.
  the places where these could happen are being marked with
  "# INVALID DATA POSSIBILITY"
- things that need to be improved are marked with "# TO DO"
- refactor the plist writing to use a XMLWriter subclass
"""


class UFONormalizerError(Exception): pass


def normalizeUFO(ufoPath, outputPath=None):
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
    # normalize layers
    if formatVersion < 3:
        if subpathExists(ufoPath, "glyphs"):
            normalizeUFO1And2GlyphsDirectory(ufoPath)
    else:
        normalizeGlyphsDirectoryNames(ufoPath)
    # normalize various files

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

def normalizeUFO1And2GlyphsDirectory(ufoPath):
    pass

def normalizeGlyphsDirectory(ufoPath, layerDirectory):
    pass

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
        return
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


# -----------------
# XML Normalization
# -----------------

# Property List

# TO DO: This should be a subclass of XML Writer instead of a bunch of functions.

def normalizePropertyList(data):
    writer = XMLWriter()
    _normalizePLISTUnknown(data, writer)
    return writer.getText()

def _normalizePLISTUnknown(data, writer):
    """
    Array:

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown([], writer)
    >>> writer.getText()
    u'<array>\\n</array>'

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(["a"], writer)
    >>> writer.getText()
    u'<array>\\n\\t<string>a</string>\\n</array>'

    Dict:

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown({}, writer)
    >>> writer.getText()
    u'<dict>\\n</dict>'

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown({"a" : "b"}, writer)
    >>> writer.getText()
    u'<dict>\\n\\t<key>a</key>\\n\\t<string>b</string>\\n</dict>'

    String:

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown("a", writer)
    >>> writer.getText()
    u'<string>a</string>'

    Boolean:

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(True, writer)
    >>> writer.getText()
    u'<true/>'

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(False, writer)
    >>> writer.getText()
    u'<false/>'

    Float:

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(1.1, writer)
    >>> writer.getText()
    u'<real>1.1</real>'

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(-1.1, writer)
    >>> writer.getText()
    u'<real>-1.1</real>'

    Integer:

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(1, writer)
    >>> writer.getText()
    u'<integer>1</integer>'

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(-1, writer)
    >>> writer.getText()
    u'<integer>-1</integer>'

    >>> writer = XMLWriter(declaration=None)
    >>> _normalizePLISTUnknown(0, writer)
    >>> writer.getText()
    u'<integer>0</integer>'

    Date:
    # TO DO: need doctests

    Data:

    >>> writer = XMLWriter(declaration=None)
    >>> data = plistlib.Data("abc")
    >>> _normalizePLISTUnknown(data, writer)
    >>> writer.getText()
    u'<data>\\n\\tYWJj\\n</data>'
    """
    if data is None:
        return
    if isinstance(data, (list, tuple)):
        _normalizePLISTArray(data, writer)
    elif isinstance(data, dict):
        _normalizePLISTDict(data, writer)
    elif isinstance(data, basestring):
        _normalizePLISTString(data, writer)
    elif isinstance(data, bool):
        _normalizePLISTBoolean(data, writer)
    elif isinstance(data, (int, long)):
        _normalizePLISTInt(data, writer)
    elif isinstance(data, float):
        _normalizePLISTFloat(data, writer)
    elif isinstance(data, plistlib.Data):
        _normalizePLISTData(data, writer)
    elif isinstance(data, datetime.datetime):
        _normalizePLISTDate(data, writer)
    else:
        raise UFONormalizerError("Unknown data type in property list: %s" % repr(type(data)))

def _normalizePLISTArray(data, writer):
    writer.beginElement("array")
    for value in data:
        _normalizePLISTUnknown(value, writer)
    writer.endElement("array")

def _normalizePLISTDict(data, writer):
    writer.beginElement("dict")
    for key, value in sorted(data.items()):
        writer.simpleElement("key", value=key)
        _normalizePLISTUnknown(value, writer)
    writer.endElement("dict")

def _normalizePLISTString(data, writer):
    writer.simpleElement("string", value=data)

def _normalizePLISTBoolean(data, writer):
    if data:
        writer.simpleElement("true")
    else:
        writer.simpleElement("false")

def _normalizePLISTFloat(data, writer):
    data = xmlConvertFloat(data)
    writer.simpleElement("real", value=data)

def _normalizePLISTInt(data, writer):
    data = xmlConvertInt(data)
    writer.simpleElement("integer", value=data)

def _normalizePLISTDate(data, writer):
    # TO DO: implement this. refer to plistlib.py.
    raise NotImplementedError

def _normalizePLISTData(data, writer):
    writer.beginElement("data")
    data = data.asBase64(maxlinelength=xmlTextMaxLineLength)
    for line in data.splitlines():
        writer.raw(line)
    writer.endElement("data")

# GLIF

def normalizeGLIF(tree):
    pass

# XML Writer

xmlTextMaxLineLength = 70
xmlIndent = u"\t"
xmlLineBreak = u"\n"
xmlAttributeOrder = u"""
""".strip().splitlines()

class XMLWriter(object):

    def __init__(self, declaration=u"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"):
        self._lines = []
        if declaration:
            self._lines.append(declaration)
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
        paragraphs = []
        for paragraph in text.splitlines():
            if not paragraph:
                paragraphs.append("")
            else:
                paragraph = textwrap.wrap(text,
                    width=xmlTextMaxLineLength,
                    expand_tabs=False,
                    replace_whitespace=False,
                    drop_whitespace=False,
                    break_long_words=False,
                    break_on_hyphens=False
                )
                paragraphs.append(paragraph)

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

    # support

    def attributesToString(self, attrs):
        """
        TO DO: need doctests
        """
        # TO DO: this ordering could probably be done more efficiently
        # maybe make the xmlAttributeOrder a dict {attr : index}
        # and use xmlAttributeOrder.get(attr, 1000000000000) instead
        # of the expensive index, two list, multiple iteration
        ordered = []
        unordered = []
        for attr, value in attrs.items():
            if attr in xmlAttributeOrder:
                index = xmlAttributeOrder.index(attr)
                ordered.append((index, attr, value))
            else:
                unordered.append((attr, value))
        compiled = [(attr, value) for index, attr, value in sorted(ordered)]
        compiled += sorted(unordered)
        formatted = []
        for attr, value in compiled:
            attr = xmlEscapeAttribute(attr)
            value = xmlConvertValue(value)
            pair = u"%s=%s" % (attr, value)
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
    TO DO: need doctests
    """
    # TO DO: needs to be handled according to the spec
    return str(value)

def xmlConvertInt(value):
    """
    TO DO: need doctests
    """
    return str(value)

# ---------------
# Path Operations
# ---------------

def duplicateUFO(inPath, outPath):
    if os.path.exists(outPath):
        shutil.rmtree(outPath)
    shutil.copytree(inPath, outPath)

def subpathJoin(ufoPath, *subpath):
    if not isinstance(subpath, basestring):
        subpath = os.path.join(*subpath)
    return os.path.join(ufoPath, subpath)

def subpathExists(ufoPath, *subpath):
    path = subpathJoin(ufoPath, *subpath)
    return os.path.exists(path)

# read

def subpathReadFile(ufoPath, *subpath):
    path = subpathJoin(ufoPath, *subpath)
    f = open(path, "rb")
    text = f.read()
    f.close()
    return text

def subpathReadPlist(ufoPath, *subpath):
    text = subpathReadFile(ufoPath, *subpath)
    return plistlib.readPlistFromString(text)

# write

def subpathWriteFile(data, ufoPath, *subpath):
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
    data = plistlib.writePlistToString(data)
    subpathWriteFile(data, ufoPath, *subpath)

# rename

def subpathRenameDirectory(ufoPath, fromSubpath, toSubpath):
    if isinstance(fromSubpath, basestring):
        fromSubpath = [fromSubpath]
    if isinstance(toSubpath, basestring):
        toSubpath = [toSubpath]
    inPath = subpathJoin(ufoPath, *fromSubpath)
    outPath = subpathJoin(ufoPath, *toSubpath)
    shutil.move(inPath, outPath)

def subpathRenameFile(ufoPath, fromSubpath, toSubpath):
    if isinstance(fromSubpath, basestring):
        fromSubpath = [fromSubpath]
    if isinstance(toSubpath, basestring):
        toSubpath = [toSubpath]
    inPath = subpathJoin(ufoPath, *fromSubpath)
    outPath = subpathJoin(ufoPath, *toSubpath)
    os.rename(inPath, outPath)

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
    import doctest
    doctest.testmod()
