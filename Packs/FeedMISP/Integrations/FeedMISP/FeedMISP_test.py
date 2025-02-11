import json
import pytest
import demistomock as demisto

from CommonServerPython import DemistoException, ThreatIntel, FeedIndicatorType
from FeedMISP import clean_user_query, build_indicators_iterator, \
    handle_file_type_fields, get_galaxy_indicator_type, build_indicators_from_galaxies, \
    update_indicator_fields, get_ip_type, Client, fetch_attributes_command


def test_build_indicators_iterator_success():
    """
     Given
        - A list of attributes returned from MISP
     When
         - Attributes are well formed
     Then
         - Create an iterator of indicators
     """
    attributes = {
        'response': {
            'Attribute': [
                {
                    'id': '123',
                    'type': 'sha256',
                    'value': '123456789',
                },
            ]
        }
    }
    attributes_iterator = build_indicators_iterator(attributes, "some_url")
    assert len(attributes_iterator) == 1
    assert attributes_iterator[0]['value'] == attributes['response']['Attribute'][0]


def test_build_indicators_iterator_fail():
    """
     Given
         - A list of attributes returned from MISP
     When
         - Attributes are not well formed
     Then
         - Raise a KeyError
     """
    with pytest.raises(KeyError):
        attributes = {"wrong_key": "some_value"}
        build_indicators_iterator(attributes, "some_url")


def test_handle_file_type_fields_simple_hash():
    """
    Given
        - Indicator created from an attribute of a hash
    When
        - Indicator contains only hash value
    Then
        - Set the hash value as a field of a matching hash name
    """
    raw_type = 'sha256'
    indicator_obj = {
        'value': 'somehashvalue',
        'type': 'File',
        'service': 'MISP',
        'fields': {}
    }
    handle_file_type_fields(raw_type, indicator_obj)
    assert indicator_obj['fields']['SHA256'] == 'somehashvalue'


def test_handle_file_type_fields_hash_and_filename():
    """
    Given
        - Indicator created from an attribute of a hash and filename
    When
        - Indicator contains both hash value and a filename
    Then
        - Set the hash value as a field of a matching hash name, update the value of the indicator
          to the hash value and add 'Associated File Names' field with the filename
    """
    raw_type = 'filename|sha256'
    indicator_obj = {
        'value': 'file.exe|somehashvalue',
        'type': 'File',
        'service': 'MISP',
        'fields': {}
    }
    handle_file_type_fields(raw_type, indicator_obj)
    assert indicator_obj['fields']['SHA256'] == 'somehashvalue'
    assert indicator_obj['fields']['Associated File Names'] == 'file.exe'
    assert indicator_obj['value'] == 'somehashvalue'


def test_clean_user_query_success():
    """
    Given
        - A json string query
    When
        - query is good
    Then
        - create a dict from json string
    """
    querystr = '{"returnFormat": "json", "type": {"OR": ["ip-src"]}, "tags": {"OR": ["tlp:%"]}}'
    params = clean_user_query(querystr)
    assert len(params) == 3


def test_clean_user_query_bad_query():
    """
    Given
        - A json string query
    When
        - json syntax is incorrect
    Then
        - raise a DemistoException
    """
    with pytest.raises(DemistoException):
        querystr = '{"returnFormat": "json", "type": {"OR": ["md5"]}, "tags": {"OR": ["tlp:%"]'
        clean_user_query(querystr)


def test_clean_user_query_change_format():
    """
    Given
        - A json parsed result from qualys
    When
        - query has a unsupported return format
    Then
        - change return format to json
    """
    querystr = '{"returnFormat": "xml", "type": {"OR": ["md5"]}, "tags": {"OR": ["tlp:%"]}}'
    params = clean_user_query(querystr)
    assert params["returnFormat"] == "json"


def test_clean_user_query_remove_timestamp():
    """
    Given
        - A json parsed result from qualys
    When
        - query has timestamp parameter
    Then
        - Return query without the timestamp parameter
    """
    good_query = '{"returnFormat": "json", "type": {"OR": ["md5"]}, "tags": {"OR": ["tlp:%"]}}'
    querystr = '{"returnFormat": "json", "timestamp": "1617875568", "type": {"OR": ["md5"]}, "tags": {"OR": ["tlp:%"]}}'
    params = clean_user_query(querystr)
    assert good_query == json.dumps(params)


def test_get_galaxy_indicator_type_success():
    """
    Given
        - Galaxy name
    When
        - Galaxy name is of a supported type
    Then
        - Return the matching indicator type
    """
    galaxy_name = 'misp-galaxy:mitre-attack-pattern="Testing - R123"'
    assert get_galaxy_indicator_type(galaxy_name) == ThreatIntel.ObjectsNames.ATTACK_PATTERN


def test_get_galaxy_indicator_type_doesnt_exist():
    """
    Given
        - Galaxy name
    When
        - Galaxy name is not supported
    Then
        - Return None
    """
    galaxy_name = 'misp-galaxy:doesnt-exist="Testing - R123"'
    assert get_galaxy_indicator_type(galaxy_name) is None


def test_build_indicators_from_galaxies():
    """
    Given
        - Indicator with galaxy tags
    When
        - Only one of the two galaxies is supported
    Then
        - Return List with an indicator created from the supported galaxy
    """
    indicator_obj = {
        'value': 'some_value',
        'type': 'IP',
        'service': 'MISP',
        'fields': {},
        'rawJSON': {
            'value': {
                'Tag': [
                    {
                        'name': 'misp-galaxy:mitre-attack-pattern="Some Value - R1234"',
                    },
                    {
                        'name': 'misp-galaxy:amitt-misinformation-pattern="fake galaxy"'
                    },
                ]
            }
        }
    }
    galaxy_indicators = build_indicators_from_galaxies(indicator_obj, 'Suspicious')
    assert len(galaxy_indicators) == 1
    assert galaxy_indicators[0]['value'] == "Some Value"
    assert galaxy_indicators[0]['type'] == ThreatIntel.ObjectsNames.ATTACK_PATTERN


@pytest.mark.parametrize(
    "indicator, feed_tags, expected_calls",
    [
        (
            {
                "value": "some_value",
                "type": "IP",
                "service": "MISP",
                "fields": {},
                "rawJSON": {
                    "value": {
                        "Tag": [
                            {
                                "name": 'misp-galaxy:mitre-attack-pattern="Some Value - R1234"',
                            }
                        ]
                    }
                },
            },
            None,
            1,
        ),
        (
            {
                "value": "some_value",
                "type": "IP",
                "service": "MISP",
                "fields": {},
                "rawJSON": {"value": {}},
            },
            ["test", "test2"],
            1,
        ),
        (
            {
                "value": "some_value",
                "type": "IP",
                "service": "MISP",
                "fields": {},
                "rawJSON": {"value": {}},
            },
            None,
            0,
        ),
    ],
)
def test_update_indicator_fields(
    mocker, indicator: dict, feed_tags: list | None, expected_calls: int
):
    """
    Given:
        - indicator and feed_tags argument
    When:
        - the update_indicator_fields function runs
    Then:
        - Ensure the update_indicator_fields function is called
          if the feed_tags argument is passed even though the indicator has no tag.
        - Ensure the update_indicator_fields function is called when the indicator has tag.
        - Ensure the update_indicator_fields function is not called
          when the indicator has no tag and no feed_tags argument is sent.
    """
    handle_tags_fields_mock = mocker.patch("FeedMISP.handle_tags_fields")

    update_indicator_fields(indicator, None, "test", feed_tags)
    assert handle_tags_fields_mock.call_count == expected_calls


@pytest.mark.parametrize('indicator, indicator_type', [
    ({'value': '1.1.1.1'}, FeedIndicatorType.IP),
    ({'value': '1.1.1.1/24'}, FeedIndicatorType.CIDR),
    ({'value': '2001:0db8:85a3:0000:0000:8a2e:0370:7334'}, FeedIndicatorType.IPv6),
    ({'value': '2001:0db8:85a3:0000:0000:8a2e:0370:7334/64'}, FeedIndicatorType.IPv6CIDR),
])
def test_get_ip_type(indicator, indicator_type):
    assert get_ip_type(indicator) == indicator_type


def test_search_query_indicators_pagination(mocker):
    """
    Given:
        - All relevant arguments for the command
    When:
        - the fetch_attributes_command function runs
    Then:
        - Ensure the pagination mechanism return the expected result (good http response is returned)
    """
    client = Client(base_url="example",
                    authorization="auth",
                    verify=False,
                    proxy=False,
                    timeout=60)
    returned_result_1 = {'response':
                         {'Attribute': [{'id': '1', 'event_id': '1', 'object_id': '0',
                                         'object_relation': None, 'category': 'Payload delivery',
                                         'type': 'sha256', 'to_ids': True, 'uuid': '5fd0c620',
                                         'timestamp': '1607517728', 'distribution': '5', 'sharing_group_id': '0',
                                         'comment': 'malspam', 'deleted': False, 'disable_correlation': False,
                                         'first_seen': None, 'last_seen': None,
                                         'value': 'val1', 'Event': {}},
                                        {'id': '2', 'event_id': '2', 'object_id': '0',
                                         'object_relation': None, 'category': 'Payload delivery',
                                         'type': 'sha256', 'to_ids': True, 'uuid': '5fd0c620',
                                         'timestamp': '1607517728', 'distribution': '5', 'sharing_group_id': '0',
                                         'comment': 'malspam', 'deleted': False, 'disable_correlation': False, 'first_seen': None,
                                         'last_seen': None, 'value': 'val2', 'Event': {}}]}}
    returned_result_2 = {'response': {'Attribute': []}}
    mocker.patch.object(Client, '_http_request', side_effect=[returned_result_1, returned_result_2])
    params_dict = {
        'type': 'attribute',
        'filters': {'category': ['Payload delivery']},
    }
    mocker.patch.object(demisto, 'setLastRun')
    mocker.patch.object(demisto, 'createIndicators')
    fetch_attributes_command(client, params_dict)
    indicators = demisto.createIndicators.call_args[0][0]
    assert len(indicators) == 2


def test_search_query_indicators_pagination_bad_case(mocker):
    """
    Given:
        - All relevant arguments for the command
    When:
        - the fetch_attributes_command function runs
    Then:
        - Ensure the pagination mechanism raises an error (bad http response is returned)
    """
    from CommonServerPython import DemistoException
    client = Client(base_url="example",
                    authorization="auth",
                    verify=False,
                    proxy=False,
                    timeout=60)
    returned_result = {'Error': 'failed api call'}
    expected_result = "Error in API call - check the input parameters and the API Key. Error: failed api call"
    mocker.patch.object(Client, '_http_request', return_value=returned_result)
    params_dict = {
        'type': 'attribute',
        'filters': {'category': ['Payload delivery']}
    }
    with pytest.raises(DemistoException) as e:
        fetch_attributes_command(client, params_dict)
    assert str(e.value) == expected_result
