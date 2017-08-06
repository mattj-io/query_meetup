# -*- mode: python -*-

block_cipher = None


a = Analysis(['query_meetup.py'],
             pathex=['venv/lib/python2.7/site-packages', '/Users/matt/Dev/meetup'],
             binaries=[],
             datas=[('venv/lib/python2.7/site-packages/meetup/api_specification/meetup_v1_services.json', 'meetup/api_specification'),
                    ('venv/lib/python2.7/site-packages/meetup/api_specification/meetup_v2_services.json', 'meetup/api_specification'),
                    ('venv/lib/python2.7/site-packages/meetup/api_specification/meetup_v3_services.json', 'meetup/api_specification')],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name='query_meetup',
          debug=False,
          strip=False,
          upx=True,
          console=True )
