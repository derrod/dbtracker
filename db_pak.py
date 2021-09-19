import struct

# simple reader for Diabotical .dbp files


class DBPFile(object):
    def __init__(self):
        self.name = ''
        self.offset = 0
        self.size = 0


class DBPReader(object):
    magic = 'DBP1'

    def __init__(self):
        self.index = []
        self.num_files = 0
        self.start_offset = 0
        self.fp = None

    def read_file(self, dbpf):
        self.fp.seek(self.start_offset + dbpf.offset)
        return self.fp.read(dbpf.size)

    @classmethod
    def read(cls, fp):
        # reads file index and returns class
        dbp = cls()
        if fp.read(4) != cls.magic:
            raise ValueError('Invalid file!')

        dbp.fp = fp
        # unknown, but appears to be always zero?
        unk = fp.read(4)
        # number of files
        dbp.num_files = struct.unpack('<I', fp.read(4))[0]

        for i in xrange(dbp.num_files):
            dbpf = DBPFile()
            name_len = struct.unpack('<I', fp.read(4))[0]
            dbpf.name = fp.read(name_len)
            dbpf.offset = struct.unpack('<I', fp.read(4))[0]
            dbpf.size = struct.unpack('<I', fp.read(4))[0]
            dbp.index.append(dbpf)

        # once all files entries are read we know the offset from where we can find the files
        dbp.start_offset = fp.tell()

        return dbp


if __name__ == '__main__':
    f = open(r'D:\Epic\Diabotical\packs\maps.dbp', 'rb')
    d = DBPReader.read(f)
    for df in d.index:
        print df.offset, df.size, df.name

    print d.read_file(d.index[0])
