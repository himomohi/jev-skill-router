from pathlib import Path
import hashlib
import os
import pytest
from jev_skill_router.catalog import Catalog,MAX_FILE_BYTES
from jev_skill_router.config import RouterError

def test_yaml_multiline_description(make_skill):
    path=make_skill(description='>\n  Debug Python\n  and tests.')
    catalog=Catalog([str(path.parent)])
    skill=next(iter(catalog.skills.values()))
    assert skill.description=='Debug Python and tests.'
    assert skill.body.startswith('Inspect')

def test_duplicate_names_have_distinct_ids(make_skill,tmp_path):
    first=make_skill(root=tmp_path/'one');second=make_skill(root=tmp_path/'two')
    cat=Catalog([str(first.parent),str(second.parent),str(first.parent)])
    assert len(cat.skills)==2
    assert len({s.id for s in cat.skills.values()})==2

def test_unsafe_yaml_rejected(make_skill):
    directory=make_skill()
    (directory/'SKILL.md').write_text('---\nname: !!python/object/apply:os.system [echo forbidden]\ndescription: bad\n---\n',encoding='utf-8')
    cat=Catalog([str(directory.parent)])
    assert not cat.skills and cat.warnings

@pytest.mark.parametrize('path',['../outside.txt','/etc/passwd','C:/secrets.txt','..\\escape.txt','.env','references/.private.md','secrets.json','binary.png'])
def test_read_blocks_unsafe_paths(skill_root,path):
    cat=Catalog([str(skill_root)]);sid=next(iter(cat.skills))
    with pytest.raises(RouterError):cat.read(sid,path)

def test_symlink_escape_blocked(skill_root,tmp_path):
    cat=Catalog([str(skill_root)]);skill=next(iter(cat.skills.values()))
    outside=tmp_path/'outside.md';outside.write_text('not a skill')
    link=skill.directory/'linked.md'
    try:link.symlink_to(outside)
    except OSError:pytest.skip('OS does not permit symlinks for this user')
    with pytest.raises(RouterError):cat.read(skill.id,'linked.md')

def test_hidden_collections_ignored(make_skill,tmp_path):
    make_skill(root=tmp_path/'skills'/'.system')
    assert not Catalog([str(tmp_path/'skills')]).skills

@pytest.mark.parametrize('newline', ['\n', '\r\n'])
def test_pagination_reassembles_exact_file(skill_root, newline):
    source = next(skill_root.rglob('SKILL.md'))
    expected = source.read_text(encoding='utf-8').replace('\n', newline)
    source.write_bytes(expected.encode('utf-8'))
    cat=Catalog([str(skill_root)]);sid=next(iter(cat.skills))
    chunks=[];offset=0
    while True:
        result=cat.read(sid,offset=offset,limit=19);chunks.append(result['content'])
        offset=result['next_offset']
        if offset is None:break
    assert ''.join(chunks)==expected

def test_edit_changes_fingerprint(skill_root):
    cat=Catalog([str(skill_root)]);old=cat.fingerprint
    next(iter(cat.skills.values())).source.write_text('---\nname: changed\ndescription: Updated\n---\nNew guidance')
    cat.refresh();assert cat.fingerprint!=old

def test_catalog_limit_fails_explicitly(make_skill,tmp_path):
    make_skill('one');make_skill('two')
    with pytest.raises(RouterError,match='max_catalog_skills'):Catalog([str(tmp_path/'skills')],limit=1)

def test_large_file_not_loaded(make_skill):
    directory=make_skill(body='x'*(MAX_FILE_BYTES+1))
    cat=Catalog([str(directory.parent)])
    assert not cat.skills and cat.warnings

@pytest.mark.parametrize('offset',[True,-1,1.2])
def test_invalid_offsets_rejected(skill_root,offset):
    cat=Catalog([str(skill_root)])
    with pytest.raises(RouterError):cat.read(next(iter(cat.skills)),offset=offset)

def test_all_bundled_examples_parse_and_csv_can_be_routed():
    from jev_skill_router.config import Config
    from jev_skill_router.router import Router
    root=Path(__file__).resolve().parents[1]/'examples/skills'
    catalog=Catalog([str(root)])
    assert len(catalog.skills)==6 and catalog.warnings==[]
    result=Router(Config(roots=[str(root)],mode='offline')).route('Profile CSV files missing values duplicate rows')
    assert result['selected'][0]['name']=='csv-profile'

@pytest.fixture
def skill_file_reads(monkeypatch):
    reads=[]
    original=Path.open
    def counted(path,mode='r',*args,**kwargs):
        if path.name=='SKILL.md' and 'r' in mode:
            reads.append(path)
        return original(path,mode,*args,**kwargs)
    monkeypatch.setattr(Path,'open',counted)
    return reads

def test_unchanged_refresh_reuses_files_and_force_reloads(make_skill,tmp_path,skill_file_reads):
    for name in ('one','two','three'):
        make_skill(name)
    cat=Catalog([str(tmp_path/'skills')]);fingerprint=cat.fingerprint
    assert len(skill_file_reads)==3
    skill_file_reads.clear()
    cat.refresh()
    reused=3
    assert len(skill_file_reads)==3-reused
    assert cat.fingerprint==fingerprint
    assert cat.refresh_stats=={'files_seen':3,'files_reused':reused,'files_reloaded':3-reused}
    skill_file_reads.clear()
    cat.refresh(force=True)
    assert len(skill_file_reads)==3
    assert cat.fingerprint==fingerprint
    assert cat.refresh_stats=={'files_seen':3,'files_reused':0,'files_reloaded':3}

def test_incremental_refresh_detects_additions_edits_and_deletions(make_skill,tmp_path,skill_file_reads):
    edited=make_skill('edited');removed=make_skill('removed');make_skill('unchanged')
    cat=Catalog([str(tmp_path/'skills')]);fingerprint=cat.fingerprint
    skill_file_reads.clear()
    (edited/'SKILL.md').write_text('---\nname: edited\ndescription: Updated\n---\nNew instructions',encoding='utf-8')
    (removed/'SKILL.md').unlink()
    added=make_skill('added')
    cat.refresh()
    expected_reads={edited/'SKILL.md',added/'SKILL.md'}
    assert set(skill_file_reads)==expected_reads
    assert {s.name for s in cat.skills.values()}=={'edited','unchanged','added'}
    assert next(s for s in cat.skills.values() if s.name=='edited').body=='New instructions'
    assert cat.fingerprint!=fingerprint
    assert cat.refresh_stats=={'files_seen':3,'files_reused':3-len(expected_reads),'files_reloaded':len(expected_reads)}

def test_missing_reliable_change_time_disables_cache(make_skill,skill_file_reads,monkeypatch):
    directory=make_skill();cat=Catalog([str(directory.parent)])
    monkeypatch.setattr('jev_skill_router.catalog.STAT_CACHE_SUPPORTED',False)
    skill_file_reads.clear()
    cat.refresh()
    assert skill_file_reads==[directory/'SKILL.md']
    assert cat.refresh_stats['files_reused']==0

def test_in_place_same_size_edit_with_restored_mtime_is_reloaded(make_skill,skill_file_reads):
    directory=make_skill(body='Before');source=directory/'SKILL.md'
    cat=Catalog([str(directory.parent)]);fingerprint=cat.fingerprint
    original_stat=source.stat()
    source.write_bytes(source.read_bytes().replace(b'Before',b'After!'))
    os.utime(source,ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
    if os.name!='nt' and source.stat().st_ctime_ns==original_stat.st_ctime_ns:
        pytest.skip('Filesystem lacks sufficiently precise change timestamps')
    skill_file_reads.clear()
    cat.refresh()
    assert skill_file_reads==[source]
    assert next(iter(cat.skills.values())).body=='After!'
    assert cat.fingerprint!=fingerprint

def test_replacement_with_same_size_and_mtime_is_reloaded(make_skill,skill_file_reads):
    directory=make_skill(body='Before')
    source=directory/'SKILL.md';original_stat=source.stat()
    cat=Catalog([str(directory.parent)]);fingerprint=cat.fingerprint
    replacement=directory/'replacement.md'
    replacement.write_bytes(source.read_bytes().replace(b'Before',b'After!'))
    os.utime(replacement,ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
    os.replace(replacement,source)
    skill_file_reads.clear()
    cat.refresh()
    assert skill_file_reads==[source]
    assert next(iter(cat.skills.values())).body=='After!'
    assert cat.fingerprint!=fingerprint

@pytest.mark.parametrize('replace_directory',[False,True])
def test_cached_skill_cannot_survive_symlink_replacement(make_skill,tmp_path,replace_directory):
    directory=make_skill();source=directory/'SKILL.md'
    cat=Catalog([str(directory.parent)])
    outside=make_skill('outside',root=tmp_path/'elsewhere')
    try:
        if replace_directory:
            directory.rename(directory.with_name('old'))
            directory.symlink_to(outside,target_is_directory=True)
            # Remove the old skill from this root's scan as well.
            (directory.with_name('old')/'SKILL.md').unlink()
        else:
            source.unlink()
            source.symlink_to(outside/'SKILL.md')
    except OSError:
        pytest.skip('OS does not permit symlinks for this user')
    cat.refresh()
    assert not cat.skills
    assert cat.refresh_stats['files_reused']==0

def test_invalid_edit_drops_previously_cached_skill(make_skill):
    directory=make_skill();cat=Catalog([str(directory.parent)])
    (directory/'SKILL.md').write_text('No frontmatter',encoding='utf-8')
    cat.refresh()
    assert not cat.skills and cat.warnings
    make_skill(body='Restored instructions')
    cat.refresh()
    assert next(iter(cat.skills.values())).body=='Restored instructions'
    assert not cat.warnings

def test_file_changed_during_read_is_not_cached(make_skill,monkeypatch):
    directory=make_skill();source=directory/'SKILL.md'
    cat=Catalog([str(directory.parent)])
    original=Catalog._text
    def changing(path):
        text=original(path)
        path.write_text(text+'\nNewly added instructions',encoding='utf-8')
        return text
    with monkeypatch.context() as patch:
        patch.setattr(Catalog,'_text',staticmethod(changing))
        cat.refresh(force=True)
    assert not cat.skills and cat.warnings
    cat.refresh()
    assert next(iter(cat.skills.values())).body.endswith('Newly added instructions')

def test_cached_catalog_does_not_cache_exact_read_output(make_skill,skill_file_reads):
    directory=make_skill();cat=Catalog([str(directory.parent)]);sid=next(iter(cat.skills))
    expected='---\r\nname: changed\r\ndescription: Changed\r\n---\r\nCurrent instructions\r\n'
    (directory/'SKILL.md').write_bytes(expected.encode('utf-8'))
    skill_file_reads.clear()
    assert cat.read(sid)['content']==expected
    assert skill_file_reads==[directory/'SKILL.md']

def test_new_skill_still_enforces_limit_after_cache_hit(make_skill,tmp_path):
    make_skill('one');cat=Catalog([str(tmp_path/'skills')],limit=1)
    make_skill('two')
    with pytest.raises(RouterError,match='max_catalog_skills'):
        cat.refresh()


def test_reparse_ancestor_is_rejected(make_skill, monkeypatch):
    from types import SimpleNamespace
    directory=make_skill()
    original=Path.lstat
    def attributes(path, *args, **kwargs):
        result=original(path,*args,**kwargs)
        if path==directory:
            return SimpleNamespace(st_mode=result.st_mode,st_file_attributes=0x400)
        return result
    monkeypatch.setattr(Path,'lstat',attributes)
    with pytest.raises(RouterError,match='reparse'):
        Catalog._no_symlinks(directory/'SKILL.md')
    assert not Catalog([str(directory.parent)]).skills


@pytest.mark.skipif(os.name!='nt',reason='Requires real Windows metadata API')
def test_windows_native_change_time_and_fallback(make_skill,skill_file_reads,monkeypatch):
    from jev_skill_router.windows_metadata import change_stamp
    directory=make_skill();source=directory/'SKILL.md'
    # Windows CI uses NTFS. Assert this path really exercises the native API,
    # rather than silently accepting fallback-only coverage.
    assert change_stamp(source) is not None
    cat=Catalog([str(directory.parent)])
    skill_file_reads.clear()
    cat.refresh()
    assert not skill_file_reads
    monkeypatch.setattr('jev_skill_router.catalog.windows_change_stamp',lambda path:None)
    cat.refresh();skill_file_reads.clear()
    cat.refresh()
    assert skill_file_reads==[source]
    assert cat.refresh_stats['files_reused']==0


@pytest.mark.skipif(os.name!='nt',reason='Requires Windows junction support')
def test_windows_junctions_are_not_traversed(make_skill,tmp_path):
    import subprocess
    directory=make_skill();source=directory/'SKILL.md'
    cat=Catalog([str(directory.parent)])
    outside=make_skill('outside',root=tmp_path/'elsewhere')
    source.unlink();directory.rmdir()
    result=subprocess.run(['cmd','/c','mklink','/J',str(directory),str(outside)],
                          capture_output=True,check=False)
    if result.returncode:
        pytest.skip('OS does not permit junction creation')
    try:
        cat.refresh()
        assert not cat.skills
        with pytest.raises(RouterError,match='reparse'):
            Catalog._no_symlinks(directory/'SKILL.md')
    finally:
        directory.rmdir()  # Remove only the junction, not its target.


@pytest.mark.parametrize('newline',['\n','\r\n'])
@pytest.mark.parametrize('bom',[b'',b'\xef\xbb\xbf'])
def test_evaluated_read_checks_full_text_digest(make_skill,newline,bom):
    directory=make_skill(body='Before');source=directory/'SKILL.md'
    raw=source.read_text(encoding='utf-8').replace('\n',newline).encode()
    source.write_bytes(bom+raw)
    cat=Catalog([str(directory.parent)]);skill=next(iter(cat.skills.values()))
    # Digest checks the complete decoded file even when returning a small page.
    result=cat.read(skill.id,limit=3,expected_digest=skill.digest)
    assert result['content']==raw.decode()[:3]
    source.write_bytes(bom+raw.replace(b'Before',b'After!'))
    with pytest.raises(RouterError,match='File changed'):
        cat.read(skill.id,limit=3,expected_digest=skill.digest)
    assert cat.read(skill.id)['content'].endswith('After!')


@pytest.mark.parametrize('path',['SKILL.md','references/guide.md'])
@pytest.mark.parametrize('changed',['same_length','shortened'])
def test_revision_bound_pagination_rejects_changed_file(make_skill,path,changed):
    directory=make_skill(body='Original instructions ' * 20)
    target=directory/path
    if path!='SKILL.md':
        target.parent.mkdir()
        target.write_text('Reference instructions ' * 20,encoding='utf-8')
    cat=Catalog([str(directory.parent)]);sid=next(iter(cat.skills))
    first=cat.read(sid,path,limit=100)
    before=target.read_bytes()
    target.write_bytes(before.replace(b'instructions',b'CHANGED_TEXT') if changed=='same_length' else b'Short')
    with pytest.raises(RouterError,match='restart reading or reroute'):
        cat.read(sid,path,offset=first['next_offset'],expected_digest=first['content_digest'])
    restarted=cat.read(sid,path)
    assert restarted['content_digest']!=first['content_digest']


@pytest.mark.parametrize('digest',[True,17,[],{},'', 'a'*63, 'a'*65, 'g'*64, 'A'*64])
def test_invalid_read_digest_is_rejected_before_file_access(make_skill,monkeypatch,digest):
    directory=make_skill();cat=Catalog([str(directory.parent)])
    monkeypatch.setattr(Catalog,'_text',staticmethod(lambda path: pytest.fail('Read malformed revision token')))
    with pytest.raises(RouterError,match='expected_digest'):
        cat.read(next(iter(cat.skills)),expected_digest=digest)


def test_wrong_read_digest_does_not_return_content(skill_root):
    cat=Catalog([str(skill_root)])
    with pytest.raises(RouterError,match='File changed'):
        cat.read(next(iter(cat.skills)),expected_digest='0'*64)


@pytest.mark.parametrize('newline',['\n','\r\n'])
@pytest.mark.parametrize('bom',[b'',b'\xef\xbb\xbf'])
def test_read_digest_is_stable_across_unicode_pages(make_skill,newline,bom):
    directory=make_skill(body='한글 설명과 café 및 🐱\n끝까지 읽으세요.'*10)
    source=directory/'SKILL.md'
    expected=source.read_text(encoding='utf-8').replace('\n',newline)
    source.write_bytes(bom+expected.encode('utf-8'))
    cat=Catalog([str(directory.parent)]);sid=next(iter(cat.skills))
    digest=hashlib.sha256(expected.encode('utf-8')).hexdigest()
    pages=[];offset=0
    while True:
        result=cat.read(sid,offset=offset,limit=19,expected_digest=digest)
        assert result['content_digest']==digest
        pages.append(result['content'])
        offset=result['next_offset']
        if offset is None:break
    assert ''.join(pages)==expected


def test_native_router_bridge_is_excluded_without_changing_disk(make_skill,skill_file_reads):
    from jev_skill_router.integrations import SKILL
    bridge=make_skill('jev-skill-router')/'SKILL.md'
    bridge.write_text(SKILL,encoding='utf-8')
    make_skill('python-debug')
    cat=Catalog([str(bridge.parent.parent)],limit=1)
    assert {s.name for s in cat.skills.values()}=={'python-debug'}
    assert not cat.warnings
    assert bridge.read_text(encoding='utf-8')==SKILL
    fingerprint=cat.fingerprint
    skill_file_reads.clear()
    cat.refresh()
    assert {s.name for s in cat.skills.values()}=={'python-debug'}
    assert cat.fingerprint==fingerprint
    assert cat.refresh_stats=={'files_seen':2,'files_reused':2,'files_reloaded':0}
    assert not skill_file_reads


def test_catalog_with_only_native_bridge_is_empty(make_skill):
    from jev_skill_router.config import Config
    from jev_skill_router.router import Router
    directory=make_skill('jev-skill-router',description='Select and load specialized skill instructions')
    router=Router(Config(roots=[str(directory.parent)],mode='offline'))
    result=router.route('Select and load specialized skill instructions')
    assert result['status']=='empty_catalog'
    assert result['selected']==[]
    assert (directory/'SKILL.md').is_file()


def test_edit_to_reserved_name_removes_cached_candidate(make_skill):
    directory=make_skill();source=directory/'SKILL.md'
    cat=Catalog([str(directory.parent)])
    original=source.read_text(encoding='utf-8')
    source.write_text(original.replace('name: python-debug','name: jev-skill-router'),encoding='utf-8')
    cat.refresh()
    assert not cat.skills and not cat.warnings
    source.write_text(original,encoding='utf-8')
    cat.refresh()
    assert {s.name for s in cat.skills.values()}=={'python-debug'}


def test_root_aliases_do_not_duplicate_skills_or_exceed_limit(make_skill):
    directory=make_skill();root=directory.parent
    cat=Catalog([str(root),str(root/'..'/root.name)],limit=1)
    baseline=Catalog([str(root)],limit=1)
    assert list(cat.skills)==list(baseline.skills)
    assert cat.refresh_stats['files_seen']==1
    assert not cat.warnings
    cat.refresh()
    assert cat.refresh_stats=={'files_seen':1,'files_reused':1,'files_reloaded':0}


def test_root_normalization_does_not_hide_symlink_ancestors(make_skill,tmp_path):
    directory=make_skill();root=directory.parent
    outside=tmp_path/'outside';outside.mkdir()
    link=root/'link'
    try:link.symlink_to(outside,target_is_directory=True)
    except OSError:pytest.skip('OS does not permit symlinks for this user')
    alias=link/'..'/root.name
    assert alias.resolve()==root.resolve()
    cat=Catalog([str(alias)])
    assert not cat.skills
    assert 'Symbolic links and reparse points' in cat.warnings[0]


def test_unreadable_subdirectory_is_reported_without_exception_details(make_skill,monkeypatch):
    good=make_skill('good');denied=make_skill('denied')
    original=os.scandir
    def denied_scandir(path):
        if Path(path)==denied:
            raise PermissionError(13,'PRIVATE_EXCEPTION_DETAILS',str(denied))
        return original(path)
    monkeypatch.setattr(os,'scandir',denied_scandir)
    cat=Catalog([str(good.parent)])
    assert {s.name for s in cat.skills.values()}=={'good'}
    assert cat.warnings==[f'{denied}: unreadable skill directory']
    assert 'PRIVATE_EXCEPTION_DETAILS' not in str(cat.warnings)


@pytest.mark.parametrize('frontmatter,reason',[
    ('name: example','invalid description'),
    ('description: example','invalid name'),
    ('- example','frontmatter must be a mapping'),
    ('name: [PRIVATE_SOURCE_TEXT\ndescription: example','invalid YAML frontmatter'),
])
def test_invalid_metadata_warning_is_actionable_and_safe(make_skill,frontmatter,reason):
    directory=make_skill();source=directory/'SKILL.md'
    source.write_text('---\n'+frontmatter+'\n---\nbody',encoding='utf-8')
    cat=Catalog([str(directory.parent)])
    assert not cat.skills
    assert cat.warnings==[f'{source}: {reason}']
    assert 'PRIVATE_SOURCE_TEXT' not in str(cat.warnings)
