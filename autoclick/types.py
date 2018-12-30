import pathlib
from typing import NewType


ReadablePath = NewType("ReadablePath", pathlib.Path)
ReadableFile = NewType("ReadableFile", pathlib.Path)
ReadableDir = NewType("ReadableDir", pathlib.Path)