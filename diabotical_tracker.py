import os
import requests
import hashlib
import json

from requests.auth import HTTPBasicAuth
from manifest import Manifest, Chunk

from db_pak import DBPReader


class EGSAPI(object):
    _user_agent = 'UELauncher/10.13.1-11497744+++Portal+Release-Live Windows/10.0.18363.1.256.64bit'
    # required for the oauth request
    _user_basic = '34a02cf8f4414e29b15921876da36f9a'
    _pw_basic = 'daafbccc737745039dffe53d94fc76cf'

    _oauth_host = 'account-public-service-prod03.ol.epicgames.com'
    _launcher_host = 'launcher-public-service-prod06.ol.epicgames.com'

    def __init__(self):
        self.session = requests.session()
        self.session.headers['User-Agent'] = self._user_agent
        self._oauth_basic = HTTPBasicAuth(self._user_basic, self._pw_basic)

        self.access_token = None
        self.user = None

    def start_session(self, refresh_token):
        params = dict(grant_type='refresh_token',
                      refresh_token=refresh_token,
                      token_type='eg1')

        r = self.session.post('https://{}/account/api/oauth/token'.format(self._oauth_host),
                              data=params, auth=self._oauth_basic)

        r.raise_for_status()
        self.user = r.json()
        self.session.headers['Authorization'] = 'bearer {}'.format(self.user["access_token"])
        return self.user

    def get_game_versions(self):
        r = self.session.get('https://{}/launcher/api/public/assets/Windows'.format(self._launcher_host),
                             params=dict(label='Live'))
        r.raise_for_status()
        return r.json()

    def get_game_manifest(self, namespace, catalogitemid, appname):
        r = self.session.get('https://{}/launcher/api/public/assets/v2/platform/Windows/namespace/{}/catalogItem/'
                             '{}/app/{}/label/Live'.format(self._launcher_host, namespace, catalogitemid, appname))
        r.raise_for_status()
        return r.json()


if __name__ == '__main__':
    update_git = True
    force_download = False
    manifest_override = ''
    base_urls = [
        'http://epicgames-download1.akamaized.net/Builds/Org/o-376adequh7aazkj2cky8h6aezvju5h/a3d939efc70848baaf996f6040d9cb19/default',
        'http://download.epicgames.com/Builds/Org/o-376adequh7aazkj2cky8h6aezvju5h/a3d939efc70848baaf996f6040d9cb19/default',
        'http://download2.epicgames.com/Builds/Org/o-376adequh7aazkj2cky8h6aezvju5h/a3d939efc70848baaf996f6040d9cb19/default',
        'http://download3.epicgames.com/Builds/Org/o-376adequh7aazkj2cky8h6aezvju5h/a3d939efc70848baaf996f6040d9cb19/default',
        'http://download4.epicgames.com/Builds/Org/o-376adequh7aazkj2cky8h6aezvju5h/a3d939efc70848baaf996f6040d9cb19/default'
    ]

    prefixes = [
        'diabotical.exe',
        'actions.cfg',
        'autodecals/',
        'maps/',
        'mods/',
        'scripts/',
        'ui/',
        'packs/'
    ]

    if os.name == 'nt':
        dl_folder = r'D:\Epic\test'
        final_exe_path = 'diabotical.exe'
    else:
        dl_folder = '/home/ubuntu/dbtracker/DiaboticalTracker'
        final_exe_path = '/home/ubuntu/dbtracker/diabotical.exe'

    s = requests.session()
    s.headers.update({
        'User-Agent': 'EpicGamesLauncher/10.14.2-12166693+++Portal+Release-Live Windows/10.0.18363.1.256.64bit'
    })

    chunks_dir = os.path.join(dl_folder, '.cache')
    meta_dir = os.path.join(dl_folder, '.cache_meta')
    manifest_dir = os.path.join(dl_folder, '.manifests')

    if not os.path.exists(chunks_dir):
        os.makedirs(chunks_dir)
    if not os.path.exists(meta_dir):
        os.makedirs(meta_dir)
    if not os.path.exists(manifest_dir):
        os.makedirs(manifest_dir)

    old_manifest = None
    old_manifest_f = os.path.join(meta_dir, 'manifest.bin')
    if os.path.exists(old_manifest_f):
        print 'Reading old manifest...'
        old_manifest = Manifest.read_all(open(old_manifest_f, 'rb').read())
        print 'Old manifest build version: {}'.format(old_manifest.meta.build_version)

    if manifest_override:
        manifest_data = open(manifest_override, 'rb').read()
    else:
        # login to epic, get data, download manifest
        egs = EGSAPI()
        base_urls = []
        egs_auth_info = json.load(open('egs_token.json'))
        egs_auth_info = egs.start_session(egs_auth_info['refresh_token'])
        json.dump(egs_auth_info, open('egs_token.json', 'wb'), indent=2, sort_keys=True)

        app = None
        for v in egs.get_game_versions():
            if v['appName'] == 'Honeycreeper':
                app = v
                break

        if old_manifest and not force_download:
            if old_manifest.meta.build_version == app['buildVersion']:
                print 'Version is already downloaded! Exiting...'
                exit(0)

        manifest_data = egs.get_game_manifest(app['namespace'], app['catalogItemId'],
                                              app['appName'])

        for element in manifest_data['elements']:
            for manifest in element['manifests']:
                base_urls.append(manifest['uri'].rpartition('/')[0])
                if 'queryParams' in manifest:
                    params = '&'.join('{}={}'.format(p['name'], p['value']) for p in manifest['queryParams'])
                    manifest['uri'] = '?'.join((manifest['uri'], params))
                print 'Downloading:', manifest['uri']
                r = s.get(manifest['uri'])
                if r.status_code != 200:
                    print 'Failed:', r.url
                    continue
                manifest_data = r.content
                break
            else:
                print 'Could not find manifest?!'

    try:
        m = Manifest.read_all(manifest_data)
        print 'Read manifest:'
        print 'App name: {}\nBuild version: {}\n'.format(m.meta.app_name,
                                                         m.meta.build_version)
    except Exception as e:
        print 'Reading manifest failed:', repr(e)
        exit(1)

    total_size = 0
    chunk_size = 0
    dl_size = 0
    files_to_dl = []
    chunk_guids = set()

    file_list = []

    for fl in m.file_manifest_list.elements:
        file_list.append((fl.sha_hash, fl.filename))

        fname = fl.filename
        if any(fname.startswith(prefix) for prefix in prefixes):
            files_to_dl.append(fl)
            total_size += fl.file_size

            if fname.startswith('packs') and not ('scripts' in fname or 'maps' in fname):
                # only download the first ~10 MiB for packs since we only really need the file list
                sizes = 0
                for cp in fl.chunk_parts:
                    if sizes >= 1024*1024*10:
                        break
                    chunk_guids.add(cp.guid_str)
                    sizes += cp.size
            else:
                for cp in fl.chunk_parts:
                    chunk_guids.add(cp.guid_str)

    hash_list = []
    for sha, name in sorted(file_list, key=lambda a: a[1]):
        hash_list.append(u'{}\t{}'.format(sha.encode('hex'), name))
    hash_list.append('')

    chunks_to_dl = []
    for chunk in m.chunk_data_list.elements:
        if chunk.guid_str in chunk_guids:
            chunk_size += chunk.window_size
            dl_size += chunk.file_size
            chunks_to_dl.append(chunk)

    # base_urls = m.custom_fields['BaseUrl'].split(',')
    print 'Files to download:', len(files_to_dl)
    print 'Total size: {:.02f} MiB'.format(total_size / 1024. / 1024.)
    print 'Chunks to download:', len(chunk_guids)
    print 'Total chunk size (compressed): {:.02f} MiB'.format(dl_size / 1024. / 1024.)
    print 'Total chunk size (uncompressed): {:.02f} MiB'.format(chunk_size / 1024. / 1024.)

    open(os.path.join(dl_folder, 'files.sha1'), 'wb').write(u'\n'.join(hash_list).encode('utf-8'))

    meta_hashes = dict()
    meta_hashes_file = os.path.join(meta_dir, 'chunks.json')
    if os.path.exists(meta_hashes_file):
        meta_hashes = json.load(open(meta_hashes_file))

    if old_manifest.meta.build_version == m.meta.build_version:
        print 'New manifest version as old manifest, disabling git...\n'
        update_git = False

    for chunk in chunks_to_dl:
        chunk_f = os.path.join(chunks_dir, '{}.chunk'.format(chunk.guid_str))

        if chunk.guid_str in meta_hashes:
            if meta_hashes[chunk.guid_str] != chunk.sha_hash.encode('hex'):  # redownload
                print 'Hash for {} doesn\'t match, redownloading...'.format(chunk.guid_str)
                os.remove(chunk_f)

        meta_hashes[chunk.guid_str] = chunk.sha_hash.encode('hex')

        if os.path.exists(chunk_f):
            continue

        print 'Downloading', chunk.path
        r = s.get(base_urls[0] + '/' + chunk.path)
        c_tmp = Chunk.read_buffer(r.content)
        open(chunk_f, 'wb').write(c_tmp.data)
        del c_tmp

    chunks_required = set(c.guid_str for c in chunks_to_dl)
    for cached_chunk in os.listdir(chunks_dir):
        c_guid = cached_chunk.rpartition('.')[0]
        if c_guid not in chunks_required:
            print 'Chunk can be deleted:', cached_chunk
            os.remove(os.path.join(chunks_dir, cached_chunk))
            del meta_hashes[c_guid]

    json.dump(meta_hashes, open(meta_hashes_file, 'wb'), indent=2, sort_keys=True)

    # determine which files we can skip:
    if old_manifest:
        old_files = dict()

        for fl in old_manifest.file_manifest_list.elements:
            if any(fl.filename.startswith(prefix) for prefix in prefixes):
                old_files[fl.filename] = fl

        old_fnames = set(old_files.keys())
        new_fnames = set(i.filename for i in files_to_dl)

        deleted_files = old_fnames - new_fnames
        print 'Deleted files:', len(deleted_files)

        for f in deleted_files:
            try:
                os.remove(os.path.join(dl_folder, f))
            except OSError as e:
                print 'Failed deleting old file:', repr(e)

        _files_to_dl = []
        for f in files_to_dl:
            old_file = old_files.get(f.filename, None)
            if not old_file:
                print 'New file:', f.filename
                _files_to_dl.append(f)
            elif old_file.sha_hash != f.sha_hash:
                print 'File changed:', f.filename
                _files_to_dl.append(f)
            elif not os.path.exists(os.path.join(dl_folder, f.filename)):
                print 'File missing:', f.filename
                _files_to_dl.append(f)

        files_to_dl = _files_to_dl

    packs_changed = set()

    for f in files_to_dl:
        f_dir, f_name = os.path.split(f.filename)
        f_dir = os.path.join(dl_folder, f_dir)
        f_path = os.path.join(f_dir, f_name)

        if 'packs' in f_dir:
            packs_changed.add(f_name)

        if not os.path.exists(f_dir):
            os.makedirs(f_dir)

        written_sha = hashlib.sha1()

        with open(f_path, 'wb') as gf:
            print 'Writing', f_path
            for cp in f.chunk_parts:
                chunk_f = os.path.join(chunks_dir,
                                       '{}.chunk'.format(cp.guid_str))
                if f.filename.startswith('packs') and not os.path.exists(chunk_f):
                    print 'Finished extracting limited parts for pack, breaking...'
                    break

                with open(chunk_f, 'rb') as cpf:
                    cpf.seek(cp.offset)
                    _tmp = cpf.read(cp.size)
                    written_sha.update(_tmp)
                    gf.write(_tmp)

        hash_matches = written_sha.digest() == f.hash
        if not hash_matches and not f.filename.startswith('packs'):
            print 'Hash mismatch! File:', f_path

        # on linux, just get strings from exe and then delete it
        if os.name != 'nt' and f_name.endswith('.exe'):
            os.system('strings -n 5 "{}" > "{}.strings"'.format(f_path, f_path))
            # move exe to other dir for further analysis
            if os.path.exists(final_exe_path):
                os.remove(final_exe_path)
            os.rename(f_path, final_exe_path)
            open(final_exe_path + '.meta', 'wb').write(m.meta.build_version)

    open(old_manifest_f, 'wb').write(manifest_data)
    manifest_name = 'diabotical_{}.manifest'.format(m.meta.build_version.strip())
    manifests_f = os.path.join(manifest_dir, manifest_name)
    if not os.path.exists(manifests_f):
        print 'Saving manifest to', manifests_f
        open(manifests_f, 'wb').write(manifest_data)

    # read DBP files and create index lists, also extract scripts
    for fname in os.listdir('DiaboticalTracker/packs'):
        if fname.endswith('.files'):
            continue

        f = open('DiaboticalTracker/packs/{}'.format(fname), 'rb')
        dbp = DBPReader.read(f)
        filenames = sorted(('{}\t\t{:d}'.format(df.name.strip(), df.size) for df in dbp.index),
                           key=lambda a: a.partition('\t\t')[0].lower())
        open('DiaboticalTracker/packs/{}.files'.format(fname), 'wb').write('\n'.join(filenames))
        if fname == 'scripts.dbp' or fname == 'maps.dbp':
            if fname not in packs_changed:
                print 'DBP "{}" not changed, skipping...'.format(fname)
                continue

            for dbf in dbp.index:
                # fix path
                fname = dbf.name.replace('\\', '/')
                fpath = os.path.join('DiaboticalTracker/', fname)
                print 'Extracting dbp file:', fpath
                fdir = os.path.split(fpath)[0]
                if not os.path.exists(fdir):
                    print 'Creating missing directory:', fdir
                    os.makedirs(fdir)

                open(fpath, 'wb').write(dbp.read_file(dbf))

    if os.name != 'nt' and update_git:
        os.system('cd DiaboticalTracker && git add .manifests/ && git commit -m "[Manifests] {}" && cd ..'.format(m.meta.build_version))
        os.system('cd DiaboticalTracker && git add scripts/ && git add mods/ && git commit -m "[Scripts] {}" && cd ..'.format(m.meta.build_version))
        os.system('cd DiaboticalTracker && git add packs/ && git commit -m "[Packs] {}" && cd ..'.format(m.meta.build_version))
        os.system('cd DiaboticalTracker && git add ui/ && git commit -m "[UI] {}" && cd ..'.format(m.meta.build_version))
        os.system('cd DiaboticalTracker && git add files.sha1 && git commit -m "[File List] {}" && cd ..'.format(m.meta.build_version))
        os.system('cd DiaboticalTracker && git add diabotical.exe.strings && git commit -m "[EXE Strings] {}" && cd ..'.format(m.meta.build_version))
        os.system('cd DiaboticalTracker && git add . && git commit -m "[Misc] {}" && cd ..'.format(m.meta.build_version))
