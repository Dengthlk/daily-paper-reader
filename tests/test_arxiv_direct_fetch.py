import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('direct_fetch', ROOT / 'src/maintain/fetchers/fetch_arxiv.py')
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


def test_configured_query_and_date_survive_split_retry():
    start = datetime(2026, 10, 25, tzinfo=timezone.utc)
    client = Mock()
    client.results.side_effect = [RuntimeError('temporary failure'), iter([]), iter([])]
    query = 'all:"reinforcement learning" OR all:"game agents"'
    fetch.fetch_category_in_windows(client, 'subscription', [(start, start + timedelta(days=4))], set(), {}, query_prefix=query)
    searches = [call.args[0].query for call in client.results.call_args_list]
    assert len(searches) == 3
    assert all(q.startswith(f'({query}) AND submittedDate:[') for q in searches)
    assert searches[1] != searches[2]


def test_unavailable_arxiv_does_not_publish_empty_or_advance_state(tmp_path):
    output = tmp_path / 'papers.json'
    output.write_text('[{"id":"existing"}]')
    with patch.object(fetch, 'load_config', return_value={'supabase': {'enabled': False}}), \
         patch.object(fetch.arxiv, 'Client') as client, \
         patch.object(fetch, 'save_seen_state') as save_seen, \
         patch.object(fetch, 'save_last_crawl_at') as save_crawl:
        client.return_value.results.side_effect = RuntimeError('source unavailable')
        with pytest.raises(RuntimeError, match='arXiv retrieval failed'):
            fetch.fetch_all_domains_metadata_robust(days=1, output_file=str(output), ignore_seen=True, disable_supabase_read=True)
        assert output.read_text() == '[{"id":"existing"}]'
        save_seen.assert_not_called()
        save_crawl.assert_not_called()


def test_successful_empty_query_is_not_an_error():
    now = datetime.now(timezone.utc)
    client = Mock()
    client.results.return_value = iter([])
    assert fetch.fetch_category_in_windows(client, 'cs', [(now-timedelta(days=1), now)], set(), {}) is None
    assert client.results.call_args.args[0].query.startswith('(cat:cs*) AND submittedDate:')
