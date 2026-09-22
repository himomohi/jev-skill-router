from pathlib import Path
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
