"""Deliver a validated account ZIP, without exposing raw network captures."""
import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath


def inspect_account_zip(path):
    path=Path(path)
    if not path.is_file():raise ValueError('没有可交付的账号ZIP，请先成功采集账号数据。')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if sum(item.file_size for item in entries)>512*1024*1024:raise ValueError('账号ZIP过大。')
        names=[item.filename for item in entries]
        if len(names)!=len(set(names)):raise ValueError('账号ZIP含重名文件。')
        for item in entries:
            name=item.filename
            parts=PurePosixPath(name)
            if parts.is_absolute() or PureWindowsPath(name).drive or '..' in parts.parts or '\\' in name:raise ValueError('账号ZIP路径不安全。')
            if (item.external_attr >> 16) & 0o170000 == 0o120000:raise ValueError('账号ZIP不能包含符号链接。')
            if item.flag_bits & 1:raise ValueError('不支持加密账号ZIP。')
            if parts.suffix.lower() in ('.etl','.pcap','.pcapng'):raise ValueError('不能把原始网络抓包当作账号ZIP交付。')
        if archive.testzip():raise ValueError('账号ZIP完整性校验失败。')
    from official_import import read_identity,captured_uid
    player,_=read_identity(path)
    uid=captured_uid(player)
    if uid<=0:raise ValueError('账号ZIP没有可确认的UID，不能交付空备份。')
    return {'uid':uid,'name':player.get('player_name',''),'bytes':path.stat().st_size}


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def export_account_zip(source,destination):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if destination.suffix.lower()!='.zip':raise ValueError('交付文件应保存为.zip。')
    if not destination.parent.is_dir():raise ValueError('请选择存在的ZIP保存目录。')
    metadata=inspect_account_zip(source)
    digest=file_hash(source)
    if source==destination.resolve():
        return dict(metadata,path=str(destination),sha256=digest)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent,prefix='.account-export-',suffix='.part',delete=False) as output:
            temporary=Path(output.name)
            with source.open('rb') as input_file:shutil.copyfileobj(input_file,output,1024*1024)
        if file_hash(temporary)!=digest:raise ValueError('账号ZIP在复制期间变化，请重新导出。')
        copied=inspect_account_zip(temporary)
        if copied['uid']!=metadata['uid']:raise ValueError('导出数据UID发生变化。')
        os.replace(temporary,destination)
        return dict(metadata,path=str(destination),sha256=digest)
    finally:
        if temporary is not None and temporary.exists():temporary.unlink()
