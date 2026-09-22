from pathlib import Path
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
    reused=0 if os.name=='nt' else 3
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
    if os.name=='nt':
        expected_reads.add(tmp_path/'skills'/'unchanged'/'SKILL.md')
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
