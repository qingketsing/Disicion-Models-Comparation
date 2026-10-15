import pytest

from decisionbench.protocol import Catalog, Sample
from orchestration.compare_main import matched_differences


def test_main_pairing_uses_each_unique_sample_once_and_keeps_discordant_outcomes():
    samples=[Sample('1','first','a'),Sample('2','second','b')]
    catalog=Catalog('v1',{'a':'first intent','b':'second intent'})
    a=[dict(sample_id='1',expected_label='a',prediction='a',status='ok'),
       dict(sample_id='2',expected_label='b',prediction='a',status='ok')]
    b=[dict(sample_id='2',expected_label='b',prediction='b',status='ok'),
       dict(sample_id='1',expected_label='a',prediction='b',status='ok')]
    differences,cases=matched_differences(samples,catalog,a,samples,catalog,b)
    assert differences==[-1,1]
    assert [c['outcome'] for c in cases]==['qwen_only','jev_only']
    with pytest.raises(ValueError,match='duplicate'):
        matched_differences(samples,catalog,a,samples,catalog,b+b[:1])
    with pytest.raises(ValueError,match='order, text or ground truth'):
        matched_differences(samples,catalog,a,samples[::-1],catalog,b)
    with pytest.raises(ValueError,match='catalog version, label order or descriptions'):
        matched_differences(samples,catalog,a,samples,Catalog('v1',dict(reversed(list(catalog.labels.items())))),b)
