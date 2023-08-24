#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import binascii
import time
import os
import shutil
from xml.etree import cElementTree as ET
import plistlib
import datetime
import glob
from collections import OrderedDict
from io import open
import logging

try:
    from ._version import __version__
except ImportError:
    try:
        from setuptools_scm import get_version
        __version__ = get_version()
    except ImportError:
        __version__ = 'unknown'

"""
- filter out unknown attributes and subelements
- add doctests for the image purging
- things that need to be improved are marked with "# TO DO"
"""

description = f"""
UFO Normalizer (version {__version__}):

This tool processes the contents of a UFO and normalizes
all possible files to a standard XML formatting, data
structure and file naming scheme.
"""


log = logging.getLogger(__name__)


def main(args=None):
    import argparse

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("input",
                        help="Path to a UFO to normalize.",
                        nargs="?")
    parser.add_argument("-t", "--test",
                        help="Run the normalizer's internal tests.",
                        action="store_true")
    parser.add_argument("-o", "--output",
                        help="Output path. If not given, "
                             "the input path will be used.")
    parser.add_argument("-a", "--all",
                        help="Normalize all files in the UFO. By default, "
                             "only files modified since the previous "
                             "normalization will be processed.",
                        action="store_true")
    parser.add_argument("-v", "--verbose",
                        help="Print more info to console.",
                        action="store_true")
    parser.add_argument("-q", "--quiet",
                        help="Suppress all non-error messages.",
                        action="store_true")
    parser.add_argument("--float-precision",
                        type=int,
                        default=DEFAULT_FLOAT_PRECISION,
                        help="Round floats to the specified number of decimal "
                             f"places (default is {DEFAULT_FLOAT_PRECISION}). "
                             "The value -1 means no "
                             "rounding (i.e. use built-in "
                             "repr().")
    parser.add_argument("-m", "--no-mod-times",
                        help="Do not write normalization time stamps.",
                        action="store_true")
    args = parser.parse_args(args)

    if args.test:
        return runTests()

    if args.verbose and args.quiet:
        parser.error("--quiet and --verbose options are mutually exclusive.")
    logLevel = "DEBUG" if args.verbose else "ERROR" if args.quiet else "INFO"
    logging.basicConfig(level=logLevel, format="%(message)s")

    if args.input is None:
        parser.error("No input path was specified.")
    inputPath = os.path.normpath(args.input)
    outputPath = args.output
    onlyModified = not args.all
    if not os.path.exists(inputPath):
        parser.error(f'Input path does not exist: "{ inputPath }".')
    if os.path.splitext(inputPath)[-1].lower() != ".ufo":
        parser.error(f'Input path is not a UFO: "{ inputPath }".')

    if args.float_precision >= 0:
        floatPrecision = args.float_precision
    elif args.float_precision == -1:
        floatPrecision = None
    else:
        parser.error("float precision must be >= 0 or -1 (no round).")

    writeModTimes = not args.no_mod_times

    message = 'Normalizing "%s".'
    if not onlyModified:
        message += " Processing all files."
    log.info(message, os.path.basename(inputPath))
    start = time.time()
    normalizeUFO(inputPath, outputPath=outputPath, onlyModified=onlyModified,
                 floatPrecision=floatPrecision, writeModTimes=writeModTimes)
    runtime = time.time() - start
    log.info("Normalization complete (%.4f seconds).", runtime)


# ---------
# Internals
# ---------

modTimeLibKey = "org.unifiedfontobject.normalizer.modTimes"
imageReferencesLibKey = "org.unifiedfontobject.normalizer.imageReferences"


def _loads(data):
    return plistlib.loads(data)


def _dumps(plist):
    return plistlib.dumps(plist)


# Python 3.9 deprecated plistlib.Data. The following _*code_base64 functions
# preserve some behavior related to that API.
def _decode_base64(s):
    if isinstance(s, str):
        return binascii.a2b_base64(s.encode("utf-8"))

    else:
        return binascii.a2b_base64(s)


def _encode_base64(s, maxlinelength=76):
    # copied from base64.encodebytes(), with added maxlinelength argument
    maxbinsize = (maxlinelength//4)*3
    pieces = []
    for i in range(0, len(s), maxbinsize):
        chunk = s[i: i + maxbinsize]
        pieces.append(binascii.b2a_base64(chunk))
    return b''.join(pieces)


# from fontTools.misc.py23
def tobytes(s, encoding='ascii', errors='strict'):
    '''no docstring'''
    if not isinstance(s, bytes):
        return s.encode(encoding, errors)
    else:
        return s


def tounicode(s, encoding='ascii', errors='strict'):
    if not isinstance(s, str):
        return s.decode(encoding, errors)
    else:
        return s


if str == bytes:
    tostr = tobytes
else:
    tostr = tounicode


class UFONormalizerError(Exception):
    pass


DEFAULT_FLOAT_PRECISION = 10
FLOAT_FORMAT = "%%.%df" % DEFAULT_FLOAT_PRECISION


def normalizeUFO(ufoPath, outputPath=None, onlyModified=True,
                 floatPrecision=DEFAULT_FLOAT_PRECISION, writeModTimes=True):
    global FLOAT_FORMAT
    if floatPrecision is None:
        # use repr() and don't round floats
        FLOAT_FORMAT = None
    else:
        # round floats to a fixed number of decimal digits
        FLOAT_FORMAT = "%%.%df" % floatPrecision
    # if the output is going to a different location,
    # duplicate the UFO to the new place and work
    # on the new file instead of trying to reconstruct
    # the file one piece at a time.
    if outputPath is not None and outputPath != ufoPath:
        duplicateUFO(ufoPath, outputPath)
        ufoPath = outputPath
    # get the UFO format version
    if not subpathExists(ufoPath, "metainfo.plist"):
        raise UFONormalizerError(f"Required metainfo.plist file not in "
                                 f"{ufoPath}")
    metaInfo = subpathReadPlist(ufoPath, "metainfo.plist")
    formatVersion = metaInfo.get("formatVersion")
    if formatVersion is None:
        raise UFONormalizerError(f"Required formatVersion value not defined "
                                 f"in metainfo.plist in {ufoPath}")
    try:
        fV = int(formatVersion)
        formatVersion = fV
    except ValueError:
        raise UFONormalizerError(f"Required formatVersion value not properly "
                                 f"formatted in metainfo.plist in {ufoPath}")
    if formatVersion > 3:
        raise UFONormalizerError(f"Unsupported UFO format "
                                 f"({formatVersion}) in {ufoPath}")
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
        availableImages = readImagesDirectory(ufoPath)
        referencedImages = set()
        normalizeGlyphsDirectoryNames(ufoPath)
        if subpathExists(ufoPath, "layercontents.plist"):
            layerContents = subpathReadPlist(ufoPath, "layercontents.plist")
            for _layerName, layerDirectory in layerContents:
                layerReferencedImages = normalizeGlyphsDirectory(
                    ufoPath, layerDirectory,
                    onlyModified=onlyModified, writeModTimes=writeModTimes)
                referencedImages |= layerReferencedImages
        imagesToPurge = availableImages - referencedImages
        purgeImagesDirectory(ufoPath, imagesToPurge)
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
    if writeModTimes:
        storeModTimes(fontLib, modTimes)
        subpathWritePlist(fontLib, ufoPath, "lib.plist")
    if subpathExists(ufoPath, "lib.plist"):
        normalizeLibPlist(ufoPath)


# ------
# Layers
# ------

def normalizeGlyphsDirectoryNames(ufoPath):
    """
    Normalize glyphs directory names following
    UFO 3 user name to file name convention.
    """
    # INVALID DATA POSSIBILITY: directory for layer name may not exist
    # INVALID DATA POSSIBILITY: directory may not be stored in layer contents
    oldLayerMapping = OrderedDict()
    if subpathExists(ufoPath, "layercontents.plist"):
        layerContents = subpathReadPlist(ufoPath, "layercontents.plist")
        for layerName, layerDirectory in layerContents:
            oldLayerMapping[layerName] = layerDirectory
    if not oldLayerMapping:
        return
    # INVALID DATA POSSIBILITY: no default layer
    # INVALID DATA POSSIBILITY: public.default used for directory other than "glyphs"
    newLayerMapping = OrderedDict()
    newLayerDirectories = set()
    for layerName, oldLayerDirectory in oldLayerMapping.items():
        if oldLayerDirectory == "glyphs":
            newLayerDirectory = "glyphs"
        else:
            newLayerDirectory = userNameToFileName(layerName,
                                                   newLayerDirectories,
                                                   prefix="glyphs.")
        newLayerDirectories.add(newLayerDirectory.lower())
        newLayerMapping[layerName] = newLayerDirectory
    # don't do a direct rename because an old directory
    # may have the same name as a new directory.
    fromTempMapping = {}
    for index, (layerName, newLayerDirectory) in enumerate(newLayerMapping.items()):
        oldLayerDirectory = oldLayerMapping[layerName]
        if newLayerDirectory == oldLayerDirectory:
            continue
        log.debug('Normalizing "%s" layer directory name to "%s".',
                  layerName, newLayerDirectory)
        tempDirectory = f"org.unifiedfontobject.normalizer.{index}"
        subpathRenameDirectory(ufoPath, oldLayerDirectory, tempDirectory)
        fromTempMapping[tempDirectory] = newLayerDirectory
    for tempDirectory, newLayerDirectory in fromTempMapping.items():
        subpathRenameDirectory(ufoPath, tempDirectory, newLayerDirectory)
    # update layercontents.plist
    newLayerMapping = list(newLayerMapping.items())
    subpathWritePlist(newLayerMapping, ufoPath, "layercontents.plist")
    return newLayerMapping


# ------
# Glyphs
# ------

def normalizeUFO1And2GlyphsDirectory(ufoPath, modTimes):
    glyphMapping = normalizeGlyphNames(ufoPath, "glyphs")
    for fileName in sorted(glyphMapping.values()):
        location = subpathJoin("glyphs", fileName)
        if subpathNeedsRefresh(modTimes, ufoPath, location):
            log.debug('Normalizing "%s".', os.path.join("glyphs", fileName))
            normalizeGLIF(ufoPath, "glyphs", fileName)
            modTimes[location] = subpathGetModTime(ufoPath, "glyphs", fileName)


def normalizeGlyphsDirectory(ufoPath, layerDirectory,
                             onlyModified=True, writeModTimes=True):
    if subpathExists(ufoPath, layerDirectory, "layerinfo.plist"):
        layerInfo = subpathReadPlist(ufoPath, layerDirectory, "layerinfo.plist")
    else:
        layerInfo = {}
    layerLib = layerInfo.get("lib", {})
    imageReferences = {}
    if onlyModified:
        stored = readImageReferences(layerLib)
        if stored is not None:
            imageReferences = stored
        else:
            # we don't know what has a reference so we must check everything
            onlyModified = False
    if onlyModified:
        modTimes = readModTimes(layerLib)
    else:
        modTimes = {}
    glyphMapping = normalizeGlyphNames(ufoPath, layerDirectory)
    for fileName in glyphMapping.values():
        if subpathNeedsRefresh(modTimes, ufoPath, layerDirectory, fileName):
            imageFileName = normalizeGLIF(ufoPath, layerDirectory, fileName)
            if imageFileName is not None:
                imageReferences[fileName] = imageFileName
            elif fileName in imageReferences:
                del imageReferences[fileName]
            modTimes[fileName] = subpathGetModTime(ufoPath, layerDirectory, fileName)
    if writeModTimes:
        storeModTimes(layerLib, modTimes)
    if imageReferences:
        storeImageReferences(layerLib, imageReferences)
    if layerLib:
        layerInfo["lib"] = layerLib
    subpathWritePlist(layerInfo, ufoPath, layerDirectory, "layerinfo.plist")
    normalizeLayerInfoPlist(ufoPath, layerDirectory)
    referencedImages = set(imageReferences.values())
    return referencedImages


def normalizeLayerInfoPlist(ufoPath, layerDirectory):
    if subpathExists(ufoPath, layerDirectory, "layerinfo.plist"):
        _normalizePlistFile({}, ufoPath, *[layerDirectory, "layerinfo.plist"],
                            preprocessor=_normalizeLayerInfoColor)


def _normalizeLayerInfoColor(obj):
    """
    - Normalize the color if specified.
    """
    if "color" in obj:
        color = obj.pop("color")
        color = _normalizeColorString(color)
        if color is not None:
            obj["color"] = color


def normalizeGlyphNames(ufoPath, layerDirectory):
    """
    Normalize GLIF file names following
    UFO 3 user name to file name convention.
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
        newFileName = userNameToFileName(str(glyphName), newFileNames, suffix=".glif")
        newFileNames.add(newFileName.lower())
        newGlyphMapping[glyphName] = newFileName
    # don't do a direct rewrite in case an old file has
    # the same name as a new file.
    fromTempMapping = {}
    for index, (glyphName, newFileName) in enumerate(sorted(newGlyphMapping.items())):
        oldFileName = oldGlyphMapping[glyphName]
        if newFileName == oldFileName:
            continue
        tempFileName = f"org.unifiedfontobject.normalizer.{index}"
        subpathRenameFile(ufoPath,
                          (layerDirectory, oldFileName),
                          (layerDirectory, tempFileName))
        fromTempMapping[tempFileName] = newFileName
    for tempFileName, newFileName in fromTempMapping.items():
        subpathRenameFile(ufoPath,
                          (layerDirectory, tempFileName),
                          (layerDirectory, newFileName))
    # update contents.plist
    subpathWritePlist(newGlyphMapping, ufoPath, layerDirectory, "contents.plist")
    # normalize contents.plist
    _normalizePlistFile({}, ufoPath, layerDirectory, "contents.plist", removeEmpty=False)
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

def _normalizePlistFile(modTimes, ufoPath, *subpath, **kwargs):
    if subpathNeedsRefresh(modTimes, ufoPath, *subpath):
        preprocessor = kwargs.get("preprocessor")
        data = subpathReadPlist(ufoPath, *subpath)
        if data:
            log.debug('Normalizing "%s".', os.path.join(*subpath))
            text = normalizePropertyList(data, preprocessor=preprocessor)
            subpathWriteFile(text, ufoPath, *subpath)
            modTimes[subpath[-1]] = subpathGetModTime(ufoPath, *subpath)
        elif kwargs.get("removeEmpty", True):
            # Don't write empty plist files, unless 'removeEmpty' is False
            log.debug('Removing empty "%s".', os.path.join(*subpath))
            subpathRemoveFile(ufoPath, *subpath)
            if subpath[-1] in modTimes:
                del modTimes[subpath[-1]]


# metainfo.plist
def normalizeMetaInfoPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "metainfo.plist", removeEmpty=False)


# fontinfo.plist
def normalizeFontInfoPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "fontinfo.plist",
                        preprocessor=_normalizeFontInfoGuidelines)


def _normalizeFontInfoGuidelines(obj):
    """
    - Follow general guideline normalization rules.
    """
    guidelines = obj.get("guidelines")
    if not guidelines:
        return
    normalized = []
    for guideline in guidelines:
        guideline = _normalizeDictGuideline(guideline)
        if guideline is not None:
            normalized.append(guideline)
    obj["guidelines"] = normalized


def _normalizeDictGuideline(guideline):
    """
    - Don't write if angle is defined but either x or y are not defined.
    - Don't write if both x and y are defined but angle is not defined.
      However <x=300 y=0> or <x=0 y=300> are allowed, and the 0 becomes None.
    """
    x = guideline.get("x")
    y = guideline.get("y")
    angle = guideline.get("angle")
    name = guideline.get("name")
    color = guideline.get("color")
    identifier = guideline.get("identifier")
    # value errors
    if x is not None:
        try:
            x = float(x)
        except ValueError:
            return
    if y is not None:
        try:
            y = float(y)
        except ValueError:
            return
    if angle is not None:
        try:
            angle = float(angle)
        except ValueError:
            return
    # The spec was ambiguous about y=0 or x=0, so don't raise an error here,
    # instead, <x=300 y=0> or <x=0 y=300> are allowed, and the 0 becomes None.
    if angle is None:
        if x == 0 and y is not None:
            x = None
        if y == 0 and x is not None:
            y = None
    # either x or y must be defined
    if x is None and y is None:
        return
    # if angle is specified, x and y must be specified
    if (x is None or y is None) and angle is not None:
        return
    # if x and y are specified, angle must be specified
    if (x is not None and y is not None) and angle is None:
        return
    normalized = {}
    if x is not None:
        normalized["x"] = x
    if y is not None:
        normalized["y"] = y
    if angle is not None:
        normalized["angle"] = angle
    if name is not None:
        normalized["name"] = name
    if color is not None:
        color = _normalizeColorString(color)
        if color is not None:
            normalized["color"] = color
    if identifier is not None:
        normalized["identifier"] = identifier
    return normalized


# groups.plist

def normalizeGroupsPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "groups.plist")


# kerning.plist

def normalizeKerningPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "kerning.plist")


# layercontents.plist

def normalizeLayerContentsPlist(ufoPath, modTimes):
    _normalizePlistFile(modTimes, ufoPath, "layercontents.plist", removeEmpty=False)


# lib.plist

def normalizeLibPlist(ufoPath):
    _normalizePlistFile({}, ufoPath, "lib.plist")


# -----------------
# XML Normalization
# -----------------

# Property List

def normalizePropertyList(data, preprocessor=None):
    if preprocessor is not None:
        preprocessor(data)
    writer = XMLWriter(isPropertyList=True)
    writer.beginElement("plist", attrs=dict(version="1.0"))
    writer.propertyListObject(data)
    writer.endElement("plist")
    writer.raw("")
    return writer.getText()


# GLIF

def normalizeGLIFString(text, glifPath=None, imageFileRef=None):
    tree = ET.fromstring(text)
    glifVersion = tree.attrib.get("format")
    if glifVersion is None:
        msg = "Undefined GLIF format"
        if glifPath is not None:
            msg += ": %s" % glifPath
        raise UFONormalizerError(msg)
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

    if imageFileRef is None:
        imageFileRef = []

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
        imageFileRef.append(image.attrib.get("fileName"))
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
    writer.raw("")
    return writer.getText()


def normalizeGLIF(ufoPath, *subpath):
    """
    - Normalize the mark color if specified.

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
    imageFileRef = []
    normalizedText = normalizeGLIFString(text, glifPath, imageFileRef)
    subpathWriteFile(normalizedText, ufoPath, *subpath)
    # return the image reference
    imageFileName = imageFileRef[0] if imageFileRef else None
    return imageFileName


def _normalizeGlifUnicode(element, writer):
    """
    - Don't write unicode element if hex attribute is not defined.
    - Don't write unicode element if value for hex value is not a proper hex value.
    - Write hex value as all uppercase, zero padded string.
    """
    v = element.attrib.get("hex")
    # INVALID DATA POSSIBILITY: no hex value
    if v:
        # INVALID DATA POSSIBILITY: invalid hex value
        try:
            d = int(v, 16)
            v = f"{d:04X}"
        except ValueError:
            return
    else:
        return
    writer.simpleElement("unicode", attrs=dict(hex=v))


def _normalizeGlifAdvance(element, writer):
    """
    - Don't write default values (width=0, height=0)
    - Ignore values that can't be converted to a number.
    - Don't write an empty element.
    """
    # INVALID DATA POSSIBILITY: value that can't be converted to float
    w = element.attrib.get("width", "0")
    h = element.attrib.get("height", "0")
    try:
        w = float(w)
        h = float(h)
    except ValueError:
        return
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
    - Don't write if fileName is not defined.
    """
    # INVALID DATA POSSIBILITY: no file name defined
    # INVALID DATA POSSIBILITY: non-existent file referenced
    fileName = element.attrib.get("fileName")
    if not fileName:
        return
    attrs = dict(
        fileName=fileName
    )
    transformation = _normalizeGlifTransformation(element)
    attrs.update(transformation)
    color = element.attrib.get("color")
    if color is not None:
        attrs["color"] = _normalizeColorString(color)
    writer.simpleElement("image", attrs=attrs)


def _normalizeGlifAnchor(element, writer):
    """
    - Don't write if x or y are not defined.
    """
    # INVALID DATA POSSIBILITY: no x defined
    # INVALID DATA POSSIBILITY: no y defined
    # INVALID DATA POSSIBILITY: x or y that can't be converted to float
    x = element.attrib.get("x")
    y = element.attrib.get("y")
    # x or y undefined
    if not x or not y:
        return
    # x or y improperly defined
    try:
        x = float(x)
        y = float(y)
    except ValueError:
        return
    attrs = dict(
        x=x,
        y=y
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
    - Follow general guideline normalization rules.
    """
    # INVALID DATA POSSIBILITY: x, y and angle not defined according to the spec
    # INVALID DATA POSSIBILITY: angle < 0 or > 360
    # INVALID DATA POSSIBILITY: x, y or angle that can't be converted to float
    attrs = "x y angle color name identifier".split(" ")
    converted = {}
    for attr in attrs:
        converted[attr] = element.attrib.get(attr)
    normalized = _normalizeDictGuideline(converted)
    if normalized is not None:
        writer.simpleElement("guideline", attrs=normalized)


def _normalizeGlifLib(element, writer):
    """
    - Don't write an empty element.
    """
    if not len(element):
        return
    obj = _convertPlistElementToObject(element[0])
    if obj:
        # normalize the mark color
        if "public.markColor" in obj:
            color = obj.pop("public.markColor")
            color = _normalizeColorString(color)
            if color is not None:
                obj["public.markColor"] = color
        writer.beginElement("lib")
        writer.propertyListObject(obj)
        writer.endElement("lib")


def _normalizeGlifNote(element, writer):
    """
    - Don't write an empty element.
    """
    value = element.text
    if not value:
        return
    if not value.strip():
        return
    writer.simpleElement("note", value=xmlEscapeText(value))


def _normalizeGlifOutlineFormat1(element, writer):
    """
    - Don't write an empty element.
    - Don't write an empty contour.
    - Don't write an empty component.
    - Retain contour and component order except for implied anchors in < UFO 3.
    - If the UFO format < 3, move implied anchors to the end.
    """
    if not len(element):
        return
    outline = []
    anchors = []
    for subElement in element:
        tag = subElement.tag
        if tag == "contour":
            contour = _normalizeGlifContourFormat1(subElement)
            if contour is None:
                continue
            if contour["type"] == "contour":
                outline.append(contour)
            else:
                anchors.append(contour)
        elif tag == "component":
            component = _normalizeGlifComponentFormat1(subElement)
            if component is None:
                continue
            if component is not None:
                outline.append(component)
    if not outline and not anchors:
        return
    writer.beginElement("outline")
    for obj in outline:
        t = obj.pop("type")
        if t == "contour":
            writer.beginElement("contour")
            for point in obj["points"]:
                writer.simpleElement("point", attrs=point)
            writer.endElement("contour")
        elif t == "component":
            writer.simpleElement("component", attrs=obj)
    for anchor in anchors:
        t = anchor.pop("type")
        writer.beginElement("contour")
        attrs = dict(
            type="move",
            x=anchor["x"],
            y=anchor["y"]
        )
        if "name" in anchor:
            attrs["name"] = anchor["name"]
        writer.simpleElement("point", attrs=attrs)
        writer.endElement("contour")
    writer.endElement("outline")


def _normalizeGlifContourFormat1(element):
    """
    - Don't write unknown subelements.
    """
    # INVALID DATA POSSIBILITY: unknown child element
    # INVALID DATA POSSIBILITY: unknown point type
    points = []
    for subElement in element:
        tag = subElement.tag
        if tag != "point":
            continue
        attrs = _normalizeGlifPointAttributesFormat1(subElement)
        if not attrs:
            return
        points.append(attrs)
    if not points:
        return
    # anchor
    if len(points) == 1 and points[0].get("type") == "move":
        anchor = points[0]
        anchor["type"] = "anchor"
        return anchor
    # contour
    contour = dict(type="contour", points=points)
    return contour


def _normalizeGlifPointAttributesFormat1(element):
    """
    - Don't write if x or y is undefined.
    - Don't write default smooth value (no).
    - Don't write smooth for offcurves.
    - Don't write default point type attribute (offcurve).
    - Don't write subelements.
    - Don't write smooth if undefined.
    - Don't write unknown point types.
    """
    # INVALID DATA POSSIBILITY: no x defined
    # INVALID DATA POSSIBILITY: no y defined
    # INVALID DATA POSSIBILITY: x or y that can't be converted to float
    # INVALID DATA POSSIBILITY: duplicate attributes
    x = element.attrib.get("x")
    y = element.attrib.get("y")
    if not x or not y:
        return {}
    try:
        x = float(x)
        y = float(y)
    except ValueError:
        return
    attrs = dict(
        x=x,
        y=y
    )
    typ = element.attrib.get("type", "offcurve")
    if typ not in ("move", "line", "curve", "qcurve", "offcurve"):
        return {}
    if typ != "offcurve":
        attrs["type"] = typ
        smooth = element.attrib.get("smooth")
        if smooth == "yes":
            attrs["smooth"] = "yes"
    name = element.attrib.get("name")
    if name is not None:
        attrs["name"] = name
    return attrs


def _normalizeGlifComponentFormat1(element):
    """
    - Don't write if base is undefined.
    - Don't write subelements.
    """
    # INVALID DATA POSSIBILITY: no base defined
    # INVALID DATA POSSIBILITY: unknown child element
    component = _normalizeGlifComponentAttributesFormat1(element)
    if not component:
        return
    component["type"] = "component"
    return component


def _normalizeGlifComponentAttributesFormat1(element):
    """
    - Don't write if base is not defined.
    - Don't write default transformation values.
    """
    # INVALID DATA POSSIBILITY: no base defined
    # INVALID DATA POSSIBILITY: duplicate attributes
    base = element.attrib.get("base")
    if not base:
        return {}
    attrs = dict(
        base=element.attrib["base"]
    )
    transformation = _normalizeGlifTransformation(element)
    attrs.update(transformation)
    return attrs


def _normalizeGlifOutlineFormat2(element, writer):
    """
    - Don't write an empty element.
    - Don't write an empty contour.
    - Don't write an empty component.
    - Retain contour and component order.
    - Don't write unknown subelements.
    """
    outline = []
    for subElement in element:
        tag = subElement.tag
        if tag == "contour":
            contour = _normalizeGlifContourFormat2(subElement)
            if contour:
                outline.append(contour)
        elif tag == "component":
            component = _normalizeGlifComponentFormat2(subElement)
            if component:
                outline.append(component)
    if not outline:
        return
    writer.beginElement("outline")
    for obj in outline:
        t = obj.pop("type")
        if t == "contour":
            attrs = {}
            identifier = obj.get("identifier")
            if identifier is not None:
                attrs["identifier"] = identifier
            writer.beginElement("contour", attrs=attrs)
            for point in obj["points"]:
                writer.simpleElement("point", attrs=point)
            writer.endElement("contour")
        elif t == "component":
            writer.simpleElement("component", attrs=obj)
    writer.endElement("outline")


def _normalizeGlifContourFormat2(element):
    """
    - Don't write unknown subelements.
    """
    # INVALID DATA POSSIBILITY: unknown child element
    # INVALID DATA POSSIBILITY: unknown point type
    points = []
    for subElement in element:
        tag = subElement.tag
        if tag != "point":
            continue
        attrs = _normalizeGlifPointAttributesFormat2(subElement)
        if not attrs:
            return
        points.append(attrs)
    if not points:
        return
    contour = dict(type="contour", points=points)
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        contour["identifier"] = identifier
    return contour


def _normalizeGlifPointAttributesFormat2(element):
    """
    - Follow same rules as Format 1, but allow an identifier attribute.
    """
    attrs = _normalizeGlifPointAttributesFormat1(element)
    identifier = element.attrib.get("identifier")
    if identifier is not None:
        attrs["identifier"] = identifier
    return attrs


def _normalizeGlifComponentFormat2(element):
    """
    - Folow the same rules as Format 1.
    """
    # INVALID DATA POSSIBILITY: no base defined
    # INVALID DATA POSSIBILITY: unknown child element
    component = _normalizeGlifComponentAttributesFormat2(element)
    if not component:
        return
    component["type"] = "component"
    return component


def _normalizeGlifComponentAttributesFormat2(element):
    """
    - Follow same rules as Format 1, but allow an identifier attribute.
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
    - Don't write default values.
    """
    attrs = {}
    for attr, default in _glifDefaultTransformation.items():
        value = element.attrib.get(attr, default)
        try:
            value = float(value)
        except ValueError:
            continue
        if value != default:
            attrs[attr] = value
    return attrs


def _normalizeColorString(value):
    """
    - Write the string as comma separated numbers, folowing the
      number normalization rules.
    """
    # INVALID DATA POSSIBILITY: bad color string
    # INVALID DATA POSSIBILITY: value < 0 or > 1
    if value.count(",") != 3:
        return
    try:
        r, g, b, a = (float(i) for i in value.split(","))
    except ValueError:
        return
    if any(x < 0 or x > 1 for x in (r, g, b, a)):
        return
    color = (xmlConvertFloat(i) for i in (r, g, b, a))
    return ",".join(color)


# Adapted from plistlib.datetime._date_from_string()
def _dateFromString(text):
    import re
    _dateParser = re.compile(r"(?P<year>\d\d\d\d)(?:-(?P<month>\d\d)"
                             r"(?:-(?P<day>\d\d)(?:T(?P<hour>\d\d)"
                             r"(?::(?P<minute>\d\d)"
                             r"(?::(?P<second>\d\d))?)?)?)?)?Z")
    gd = _dateParser.match(text).groupdict()
    lst = []
    for key in ('year', 'month', 'day', 'hour', 'minute', 'second'):
        val = gd[key]
        if val is None:
            break
        lst.append(int(val))
    return datetime.datetime(*lst)


def _dateToString(data):
    return (f'{data.year:04d}-{data.month:02d}-'
            f'{data.day:02d}T{data.hour:02d}:'
            f'{data.minute:02d}:{data.second:02d}Z')


def _convertPlistElementToObject(element):
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
        if not element.text:
            return ""
        return element.text
    elif tag == "data":
        if not element.text:
            return b''
        return binascii.a2b_base64(element.text)
    elif tag == "date":
        return _dateFromString(element.text)
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
xmlDeclaration = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
plistDocType = ("<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" "
                "\"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">")
xmlTextMaxLineLength = 70
xmlIndent = "\t"
xmlLineBreak = "\n"
xmlAttributeOrder = """
name
base
format
fileName
x
y
angle
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

    def simpleElement(self, tag, attrs=None, value=None):
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

    def beginElement(self, tag, attrs=None):
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
        if data is None:
            return
        if isinstance(data, (list, tuple)):
            self._plistArray(data)
        elif isinstance(data, dict):
            self._plistDict(data)
        elif isinstance(data, str):
            self._plistString(data)
        elif isinstance(data, bool):
            self._plistBoolean(data)
        elif isinstance(data, int):
            self._plistInt(data)
        elif isinstance(data, float):
            dataStr = xmlConvertFloat(data)
            try:
                data = int(dataStr)
                self._plistInt(data)
            except ValueError:
                self._plistFloat(data)
        elif isinstance(data, bytes):
            self._plistData(data)
        elif isinstance(data, datetime.datetime):
            self._plistDate(data)
        else:
            raise UFONormalizerError(f"Unknown data type in property list: "
                                     f"{repr(type(data))}")

    def _plistArray(self, data):
        self.beginElement("array")
        for value in data:
            self.propertyListObject(value)
        self.endElement("array")

    def _plistDict(self, data):
        self.beginElement("dict")
        for key, value in sorted(data.items()):
            self.simpleElement("key", value=xmlEscapeText(key))
            self.propertyListObject(value)
        self.endElement("dict")

    def _plistString(self, data):
        self.simpleElement("string", value=xmlEscapeText(data))

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
        data = _dateToString(data)
        self.simpleElement("date", value=data)

    def _plistData(self, data):
        data = _encode_base64(data, maxlinelength=xmlTextMaxLineLength)
        if not data:
            self.simpleElement("data", value="")
        else:
            self.beginElement("data")
            for line in tostr(data).splitlines():
                self.raw(line)
            self.endElement("data")

    # support

    def attributesToString(self, attrs):
        """
        - Sort the known attributes in the preferred order.
        - Sort unknown attributes in alphabetical order and
          place them after the known attributes.
        - Format as space separated name="value".
        """
        sorter = [
            (xmlAttributeOrder.get(attr, 100), attr, value) for (attr, value) in attrs.items()
        ]
        formatted = []
        for _index, attr, value in sorted(sorter):
            attr = xmlEscapeAttribute(attr)
            value = xmlConvertValue(value)
            pair = "%s=\"%s\"" % (attr, value)
            formatted.append(pair)
        return " ".join(formatted)


def xmlEscapeText(text):
    if text:
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
    return text


def xmlEscapeAttribute(text):
    text = xmlEscapeText(text)
    text = text.replace("\"", "&quot;")
    return text


def xmlConvertValue(value):
    if isinstance(value, float):
        return xmlConvertFloat(value)
    elif isinstance(value, int):
        return xmlConvertInt(value)
    value = xmlEscapeText(value)
    return value


def xmlConvertFloat(value):
    if FLOAT_FORMAT is None:
        string = repr(value)
        if "e" in string:
            string = "%.16f" % value
    else:
        string = FLOAT_FORMAT % value
    if "." in string:
        string = string.rstrip("0")
        if string[-1] == ".":
            return xmlConvertInt(int(string[:-1]))
    return string


def xmlConvertInt(value):
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
    if not isinstance(subpath, str):
        subpath = os.path.join(*subpath)
    return os.path.join(ufoPath, subpath)


def subpathSplit(path):
    """
    Split path parts.
    """
    return os.path.split(path)


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
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return text


def subpathReadPlist(ufoPath, *subpath):
    """
    Read the contents of a property list
    and convert it into a Python object.
    """
    path = subpathJoin(ufoPath, *subpath)
    with open(path, "rb") as f:
        data = f.read()
    return _loads(data)


# write

def subpathWriteFile(text, ufoPath, *subpath):
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

    if text != existing:
        # always use Unix LF end of lines
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def subpathWritePlist(data, ufoPath, *subpath):
    """
    Write a Python object to a property list.
    THIS DOES NOT WRITE NORMALIZED OUTPUT.

    This will only modify the file if the
    file contains data that is different
    from the new data.
    """
    data = _dumps(data)
    path = subpathJoin(ufoPath, *subpath)
    if subpathExists(ufoPath, *subpath):
        existing = subpathReadPlist(ufoPath, *subpath)
    else:
        existing = None

    if data != existing:
        with open(path, "wb") as f:
            f.write(data)


# rename

def subpathRenameFile(ufoPath, fromSubpath, toSubpath):
    """
    Rename a file.
    """
    if isinstance(fromSubpath, str):
        fromSubpath = [fromSubpath]
    if isinstance(toSubpath, str):
        toSubpath = [toSubpath]
    inPath = subpathJoin(ufoPath, *fromSubpath)
    outPath = subpathJoin(ufoPath, *toSubpath)
    os.rename(inPath, outPath)


def subpathRenameDirectory(ufoPath, fromSubpath, toSubpath):
    """
    Rename a directory.
    """
    if isinstance(fromSubpath, str):
        fromSubpath = [fromSubpath]
    if isinstance(toSubpath, str):
        toSubpath = [toSubpath]
    inPath = subpathJoin(ufoPath, *fromSubpath)
    outPath = subpathJoin(ufoPath, *toSubpath)
    shutil.move(inPath, outPath)


# remove

def subpathRemoveFile(ufoPath, *subpath):
    """
    Remove a file.
    """
    if subpathExists(ufoPath, *subpath):
        path = subpathJoin(ufoPath, *subpath)
        os.remove(path)


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
    Returns True if the file's latest modification time is different
    from its previous modification time.
    """
    previous = modTimes.get(subPath[-1])
    if previous is None:
        return True
    latest = subpathGetModTime(ufoPath, *subPath)
    return latest != previous


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
    return modTimes


# ----------------
# Image Management
# ----------------

def readImagesDirectory(ufoPath):
    """
    Get a listing of all images in the images directory.
    """
    pattern = subpathJoin(ufoPath, *["images", "*.png"])
    imageNames = [subpathSplit(path)[-1] for path in glob.glob(pattern)]
    return set(imageNames)


def purgeImagesDirectory(ufoPath, toPurge):
    """
    Purge specified images from the images directory.
    """
    for fileName in toPurge:
        if subpathExists(ufoPath, *["images", fileName]):
            path = subpathJoin(ufoPath, *["images", fileName])
            os.remove(path)


def storeImageReferences(lib, imageReferences):
    """
    Store the image references.
    """
    lib[imageReferencesLibKey] = imageReferences


def readImageReferences(lib):
    """
    Read the image references.
    """
    references = lib.get(imageReferencesLibKey)
    return references


# ----------------------
# User Name to File Name
# ----------------------
#
# This was taken directly from the UFO 3 specification.

illegalCharacters = '" * + / : < > ? [ \\ ] | \0'.split(" ")
illegalCharacters += [chr(i) for i in range(1, 32)]
illegalCharacters += [chr(0x7F)]
reservedFileNames = "CON PRN AUX CLOCK$ NUL A:-Z: COM1".lower().split(" ")
reservedFileNames += "LPT1 LPT2 LPT3 COM2 COM3 COM4".lower().split(" ")
maxFileNameLength = 255


class NameTranslationError(Exception):
    pass


def userNameToFileName(userName, existing=None, prefix="", suffix=""):
    """
    existing should be a case-insensitive list
    of all existing file names.
    """
    if existing is None:
        existing = []
    # the incoming name must be a string
    assert isinstance(userName, str), "The value for userName must be a string."
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


def handleClash1(userName, existing=None, prefix="", suffix=""):
    """
    existing must be a case-insensitive list
    of all existing file names.
    """
    if existing is None:
        existing = []
    # if the prefix length + user name length + suffix length + 15 is at
    # or past the maximum length, slice 15 characters off of the user name
    prefixLength = len(prefix)
    suffixLength = len(suffix)
    if prefixLength + len(userName) + suffixLength + 15 > maxFileNameLength:
        length = (prefixLength + len(userName) + suffixLength + 15)
        sliceLength = maxFileNameLength - length
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


def handleClash2(existing=None, prefix="", suffix=""):
    """
    existing must be a case-insensitive list
    of all existing file names.
    """
    if existing is None:
        existing = []
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

def _runProfile(outPath):
    normalizeUFO(outPath)


def runTests():
    # unit tests
    import unittest
    import sys
    # unittest.main() will try parsing arguments, "-t" in this case
    sys.argv = sys.argv[:1]

    testsdir = os.path.join(os.path.dirname(__file__), os.path.pardir, "tests")
    if not os.path.exists(os.path.join(testsdir, "test_ufonormalizer.py")):
        print("tests not found; run this from the source directory")
        return 1

    # make sure 'tests' folder is on PYTHONPATH so unittest can import
    sys.path.append(testsdir)

    testrun = unittest.main("test_ufonormalizer", exit=False, verbosity=2)

    # test file searching
    ufo_dir = os.path.join(testsdir, "data")
    paths = []
    pattern = os.path.join(ufo_dir, "*.ufo")
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

        cProfile.run("_runProfile('%s')" % outPath, sort="tottime")
        shutil.rmtree(outPath)

        # general test
        import time

        for inPath, outPath in paths:
            shutil.copytree(inPath, outPath)
            s = time.time()
            normalizeUFO(outPath)
            t = time.time() - s
            print(os.path.basename(inPath) + ":", t, "seconds")

    return not testrun.result.wasSuccessful()


if __name__ == "__main__":
    main()
