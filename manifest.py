import struct
import zlib
import hashlib
from cStringIO import StringIO
import os
import requests
import json

from collections import defaultdict

# ToDo JSON manifest reader

# manifest_file = 'spellbreak.manifest'
MANIFEST_HEADER_MAGIC = 0x44BEC00C
CHUNK_HEADER_MAGIC = 0xB1FE3AA2


def read_fstring(sio, return_empty=False):
    length = struct.unpack('<i', sio.read(4))[0]
    is_utf16 = False

    if length < 0:  # unicode
        length *= -2
        is_utf16 = True
    elif length == 0:
        if return_empty:
            return '<empty>'
        else:
            return ''

    if is_utf16:
        s = sio.read(length)
        return s.decode('utf-16')
    else:
        s = sio.read(length - 1)
        sio.seek(1, 1)  # skip string terminator
        return s


def read_fstring_tset(sio):
    _set = []
    entries = struct.unpack('<I', sio.read(4))[0]

    for i in xrange(entries):
        _set.append(read_fstring(sio))

    return _set


def get_chunk_dir(version):
    chunk_version = 'Chunks'
    if version >= 3:
        chunk_version = 'ChunksV2'
    if version >= 6:
        chunk_version = 'ChunksV3'
    if version >= 15:
        chunk_version = 'ChunksV4'

    return chunk_version


class Manifest(object):
    def __init__(self):
        self.header_size = 0
        self.size_compressed = 0
        self.size_uncompressed = 0
        self.sha_hash = ''
        self.stored_as = 0
        self.version = 0
        self._data = ''
        self.data = ''

        # remainder
        self.meta = None
        self.chunk_data_list = None
        self.file_manifest_list = None
        self.custom_fields = None

    @property
    def compressed(self):
        return self.stored_as & 0x1

    @classmethod
    def read_all(cls, data):
        _m = cls.read(data)
        _tmp = StringIO(_m.data)

        _m.meta = ManifestMeta.read(_tmp)
        _m.chunk_data_list = CDL.read(_tmp)
        _m.file_manifest_list = FML.read(_tmp)
        _m.custom_fields = CustomFields.read(_tmp)

        unhandled_data = _tmp.read()
        if unhandled_data:
            print 'Did not read {} bytes!'.format(len(unhandled_data))
            open('unhandled.bin', 'wb').write(unhandled_data)
            exit(1)

        return _m

    @classmethod
    def read(cls, data):
        sio = StringIO(data)
        if struct.unpack('<I', sio.read(4))[0] == MANIFEST_HEADER_MAGIC:
            print 'Magic OK!'
        else:
            raise ValueError('No header magic!')

        _manifest = cls()
        _manifest.header_size = struct.unpack('<I', sio.read(4))[0]
        _manifest.size_compressed = struct.unpack('<I', sio.read(4))[0]
        _manifest.size_ucompressed = struct.unpack('<I', sio.read(4))[0]
        _manifest.sha_hash = sio.read(20)
        _manifest.stored_as = struct.unpack('B', sio.read(1))[0]
        _manifest.version = struct.unpack('<I', sio.read(4))[0]
        _manifest._data = sio.read()
        if _manifest.compressed:
            _manifest.data = zlib.decompress(_manifest._data)
            dec_hash = hashlib.sha1(_manifest.data).hexdigest()
            if dec_hash != _manifest.sha_hash.encode('hex'):
                raise ValueError('Hash does not match!')

        # this is hacky, but required
        ChunkInfo._chunk_format = get_chunk_dir(_manifest.version)

        return _manifest


class ManifestMeta(object):
    def __init__(self):
        self.meta_size = 0
        self.data_version = 0
        self.feature_level = 0
        self.is_file_data = False
        self.app_id = 0
        self.app_name = ''
        self.build_version = ''
        self.launch_exe = ''
        self.launch_command = ''
        self.prereq_set = []
        self.prereq_name = ''
        self.prereq_path = ''
        self.prereq_args = ''

    @classmethod
    def read(cls, sio):
        _meta = cls()

        _meta.meta_size = struct.unpack('<I', sio.read(4))[0]
        _meta.data_version = struct.unpack('B', sio.read(1))[0]
        _meta.feat_lvl = struct.unpack('<I', sio.read(4))[0]
        _meta.is_file_data = struct.unpack('B', sio.read(1))[0] == 1
        _meta.app_id = struct.unpack('<I', sio.read(4))[0]
        _meta.app_name = read_fstring(sio)
        _meta.build_version = read_fstring(sio)
        _meta.launch_exe = read_fstring(sio)
        _meta.launch_command = read_fstring(sio)
        _meta.prereq_set = read_fstring_tset(sio)
        _meta.prereq_name = read_fstring(sio)
        _meta.prereq_path = read_fstring(sio)
        _meta.prereq_args = read_fstring(sio)

        if sio.tell() != _meta.meta_size:
            raise ValueError('Did not read entire meta!')

        # seek to end if not already
        # sio.seek(0 + _meta.meta_size)

        return _meta


class CDL(object):
    def __init__(self):
        self.version = 0
        self.size = 0
        self.count = 0
        self.elements = []

    @property
    def number(self):
        return len(self.elements)

    @classmethod
    def read(cls, sio):
        cdl_start = sio.tell()
        _cdl = cls()

        _cdl.size = struct.unpack('<I', sio.read(4))[0]
        _cdl.version = struct.unpack('B', sio.read(1))[0]
        _cdl.count = struct.unpack('<I', sio.read(4))[0]

        for i in xrange(_cdl.count):
            _cdl.elements.append(ChunkInfo())

        # read guid
        for chunk in _cdl.elements:
            chunk.guid.append(struct.unpack('<I', sio.read(4))[0])
            chunk.guid.append(struct.unpack('<I', sio.read(4))[0])
            chunk.guid.append(struct.unpack('<I', sio.read(4))[0])
            chunk.guid.append(struct.unpack('<I', sio.read(4))[0])

        # hash
        for chunk in _cdl.elements:
            chunk.hash = struct.unpack('<Q', sio.read(8))[0]

        # sha hash
        for chunk in _cdl.elements:
            chunk.sha_hash = sio.read(20)

        # group number
        for chunk in _cdl.elements:
            chunk.group_num = struct.unpack('B', sio.read(1))[0]

        # window size
        for chunk in _cdl.elements:
            chunk.window_size = struct.unpack('<I', sio.read(4))[0]

        # file size
        for chunk in _cdl.elements:
            chunk.file_size = struct.unpack('<q', sio.read(8))[0]

        if sio.tell() - cdl_start != _cdl.size:
            raise ValueError('Did not read entire chunk data list!')

        return _cdl


class ChunkInfo(object):
    _chunk_format = 'ChunksV4'

    def __init__(self):
        self.guid = []
        self.hash = 0
        self.sha_hash = ''
        self.group_num = 0
        self.window_size = 0
        self.file_size = 0

    def __repr__(self):
        return '<ChunkInfo (guid={}, hash={}, sha_hash={}, group_num={}, window_size={}, file_size={})>'.format(
            self.guid_str, self.hash, self.sha_hash.encode('hex'), self.group_num, self.window_size, self.file_size
        )

    @property
    def guid_str(self):
        return '-'.join('{:08x}'.format(g) for g in self.guid)

    @property
    def path(self):
        return '{}/{:02d}/{:016X}_{}.chunk'.format(
            self._chunk_format,
            (zlib.crc32(struct.pack('<I', self.guid[0]) +
                        struct.pack('<I', self.guid[1]) +
                        struct.pack('<I', self.guid[2]) +
                        struct.pack('<I', self.guid[3])) & 0xffffffff) % 100,
            self.hash, ''.join('{:08X}'.format(g) for g in self.guid)
        )


class FML(object):
    def __init__(self):
        self.version = 0
        self.size = 0
        self.count = 0
        self.elements = []

    @property
    def number(self):
        return len(self.elements)

    @classmethod
    def read(cls, sio):
        fml_start = sio.tell()
        _fml = cls()
        _fml.size = struct.unpack('<I', sio.read(4))[0]
        _fml.version = struct.unpack('B', sio.read(1))[0]
        _fml.count = struct.unpack('<I', sio.read(4))[0]

        for i in xrange(_fml.count):
            _fml.elements.append(FileManifest())

        for fm in _fml.elements:
            fm.filename = read_fstring(sio)

        for fm in _fml.elements:
            fm.symlink_target = read_fstring(sio)

        for fm in _fml.elements:
            fm.hash = sio.read(20)

        for fm in _fml.elements:
            fm.flags = struct.unpack('B', sio.read(1))[0]

        for fm in _fml.elements:
            _elem = struct.unpack('<I', sio.read(4))[0]
            for i in xrange(_elem):
                fm.install_tags.append(read_fstring(sio))

        for fm in _fml.elements:
            _elem = struct.unpack('<I', sio.read(4))[0]
            for i in xrange(_elem):
                chunkp = ChunkPart()
                _size = struct.unpack('<I', sio.read(4))[0]
                chunkp.guid.append(struct.unpack('<I', sio.read(4))[0])
                chunkp.guid.append(struct.unpack('<I', sio.read(4))[0])
                chunkp.guid.append(struct.unpack('<I', sio.read(4))[0])
                chunkp.guid.append(struct.unpack('<I', sio.read(4))[0])
                chunkp.offset = struct.unpack('<I', sio.read(4))[0]
                chunkp.size = struct.unpack('<I', sio.read(4))[0]
                fm.chunk_parts.append(chunkp)

        # calc size
        for fm in _fml.elements:
            fm.file_size = sum(c.size for c in fm.chunk_parts)

        if sio.tell() - fml_start != _fml.size:
            raise ValueError('Did not read entire chunk data list!')

        return _fml


class FileManifest(object):
    def __init__(self):
        self.filename = ''
        self.symlink_target = ''
        self.hash = ''
        self.flags = 0
        self.install_tags = []
        self.chunk_parts = []
        self.file_size = 0

    @property
    def sha_hash(self):
        return self.hash

    def __repr__(self):
        return '<FileManifest (filename="{}", symlink_target="{}", hash={}, flags={}, ' \
               'install_tags=[{}], chunk_parts=[{}], file_size={})>'.format(
            self.filename, self.symlink_target, self.hash.encode('hex'), self.flags,
            ', '.join(self.install_tags), ', '.join(repr(c) for c in self.chunk_parts),
            self.file_size)


class ChunkPart(object):
    def __init__(self):
        self.guid = []
        self.offset = 0
        self.size = 0

    @property
    def guid_str(self):
        return '-'.join('{:08x}'.format(g) for g in self.guid)

    def __repr__(self):
        guid_readable = '-'.join('{:08x}'.format(g) for g in self.guid)
        return '<ChunkPart (guid={}, offset={}, size={})>'.format(
            guid_readable, self.offset, self.size)


class CustomFields(object):
    def __init__(self):
        self.size = 0
        self.version = 0
        self.count = 0

        self._dict = dict()

    def __getitem__(self, item):
        return self._dict.get(item, None)

    def __str__(self):
        return str(self._dict)

    def keys(self):
        return self._dict.keys()

    def values(self):
        return self._dict.values()

    @classmethod
    def read(cls, sio):
        _cf = cls()

        cf_start = sio.tell()
        _cf.size = struct.unpack('<I', sio.read(4))[0]
        _cf.version = struct.unpack('B', sio.read(1))[0]
        _cf.count = struct.unpack('<I', sio.read(4))[0]

        _keys = []
        _values = []

        for i in xrange(_cf.count):
            _keys.append(read_fstring(sio))

        for i in xrange(_cf.count):
            _values.append(read_fstring(sio))

        _cf._dict = dict(zip(_keys, _values))

        if sio.tell() - cf_start != _cf.size:
            raise ValueError('Did not read entire custom fields list!')

        return _cf


class Chunk(object):
    def __init__(self):
        self.header_version = 0
        self.header_size = 0
        self.compressed_size = 0
        self.hash = 0
        self.stored_as = 0
        self.guid = []

        self.hash_type = 0
        self.sha_hash = None
        self.uncompressed_size = 1024 * 1024

        self._sio = None
        self._data = None

    @property
    def data(self):
        if self._data:
            return self._data

        if self.compressed:
            print 'Decompressing'
            self._data = zlib.decompress(self._sio.read())
        else:
            self._data = self._sio.read()

        return self._data

    @property
    def guid_str(self):
        return '-'.join('{:08x}'.format(g) for g in self.guid)

    @property
    def compressed(self):
        return self.stored_as & 0x1

    @classmethod
    def read_buffer(cls, data):
        _sio = StringIO(data)
        return cls.read(_sio)

    @classmethod
    def read(cls, sio):
        head_start = sio.tell()

        if struct.unpack('<I', sio.read(4))[0] != CHUNK_HEADER_MAGIC:
            raise ValueError('Chunk magic doesn\'t match!')

        _chunk = cls()
        _chunk._sio = sio
        _chunk.header_version = struct.unpack('<I', sio.read(4))[0]
        _chunk.header_size = struct.unpack('<I', sio.read(4))[0]
        _chunk.compressed_size = struct.unpack('<I', sio.read(4))[0]
        _chunk.guid = [struct.unpack('<I', sio.read(4))[0],
                       struct.unpack('<I', sio.read(4))[0],
                       struct.unpack('<I', sio.read(4))[0],
                       struct.unpack('<I', sio.read(4))[0]]
        _chunk.hash = struct.unpack('<Q', sio.read(8))[0]
        _chunk.stored_as = struct.unpack('B', sio.read(1))[0]

        if _chunk.header_version >= 2:
            _chunk.sha_hash = sio.read(20)
            _chunk.hash_type = struct.unpack('B', sio.read(1))[0]

        if _chunk.header_version >= 3:
            _chunk.uncompressed_size = struct.unpack('<I', sio.read(4))[0]

        if sio.tell() - head_start != _chunk.header_size:
            raise ValueError('Did not read entire chunk header!')

        return _chunk
