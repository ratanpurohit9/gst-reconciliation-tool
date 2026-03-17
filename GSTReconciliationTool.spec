# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_all

datas = [('app.py', '.'), ('modules', 'modules'), ('recon_history.db', '.'), ('C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python314\\Lib\\site-packages\\streamlit', 'streamlit')]
binaries = []
hiddenimports = ['streamlit', 'streamlit.web.cli', 'streamlit.web.server', 'streamlit.runtime', 'streamlit.runtime.scriptrunner', 'streamlit.runtime.scriptrunner.magic_funcs', 'streamlit.components.v1', 'altair', 'pandas', 'numpy', 'openpyxl', 'xlsxwriter', 'reportlab', 'reportlab.pdfgen', 'reportlab.lib', 'reportlab.lib.pagesizes', 'reportlab.lib.styles', 'reportlab.lib.units', 'reportlab.lib.colors', 'reportlab.lib.enums', 'reportlab.platypus', 'reportlab.platypus.tables', 'reportlab.platypus.flowables', 'reportlab.platypus.paragraph', 'sqlite3', 'uuid', 'modules.license_manager', 'modules.key_hashes']
datas += collect_data_files('streamlit')
tmp_ret = collect_all('streamlit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('altair')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pandas')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('reportlab')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GSTReconciliationTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GSTReconciliationTool',
)
