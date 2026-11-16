"""Count explicitly adjudicated reader feedback; never infer literary merit.

Input JSON:
  artifact_sha256: SHA-256 of the exact UTF-8 text
  questions: [{id, kind: fact|interpretation, question, criterion}]
  records: [{participant_id, reader_type: human|model, answers: [
    {question_id, response, quote, judgment, rationale}]}]

fact judgments: correct|incorrect|uncertain
interpretation judgments: supported|unsupported|uncertain
Quote the current text that supports or prompted the answer. Criterion and
rationale are human/model judgments, not computed truth. Missing answers remain
in the denominator of received records; zero feedback yields null, never zero
quality. No claim of authenticated people, independence, or population effects.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def need(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def summarize(data, text):
    need(isinstance(data, dict), 'Feedback must be an object')
    need(nonempty(text), 'Current text must be nonempty')
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    need(data.get('artifact_sha256') == digest, 'Feedback belongs to a different text version')
    questions = data.get('questions')
    need(isinstance(questions, list) and questions, 'Define questions and criteria before counting')
    by_id = {}
    for question in questions:
        need(isinstance(question, dict), 'Question must be an object')
        for key in ('id', 'question', 'criterion'):
            need(nonempty(question.get(key)), 'Question requires ' + key)
        need(question.get('kind') in ('fact', 'interpretation'), 'Unknown question kind')
        need(question['id'] not in by_id, 'Duplicate question ID')
        by_id[question['id']] = question
    records = data.get('records')
    need(isinstance(records, list), 'Records must be a list; use [] for unmeasured')
    groups = {'human': [], 'model': []}
    identities = set()
    for record in records:
        need(isinstance(record, dict), 'Record must be an object')
        need(nonempty(record.get('participant_id')), 'Record requires participant_id')
        kind = record.get('reader_type')
        need(isinstance(kind, str) and kind in groups, 'Reader type must be human or model')
        identity = (kind, record['participant_id'])
        need(identity not in identities, 'Duplicate participant within a reader group')
        identities.add(identity)
        answers = record.get('answers')
        need(isinstance(answers, list), 'Answers must be a list; [] records a missing answer')
        indexed = {}
        for answer in answers:
            need(isinstance(answer, dict), 'Answer must be an object')
            question_id = answer.get('question_id')
            need(isinstance(question_id, str) and question_id in by_id, 'Answer has an unknown question')
            need(question_id not in indexed, 'Duplicate answer for a question')
            for key in ('response', 'quote', 'rationale'):
                need(nonempty(answer.get(key)), 'Answer requires ' + key)
            need(answer['quote'] in text, 'Answer quote is not in the current text')
            outcomes = ('correct', 'incorrect', 'uncertain') if by_id[question_id]['kind'] == 'fact' else ('supported', 'unsupported', 'uncertain')
            need(answer.get('judgment') in outcomes, 'Judgment must match the question kind')
            indexed[question_id] = answer
        groups[kind].append(indexed)
    report = {'version': 1, 'artifact_sha256': digest,
              'denominator': 'received unique participant records within each reader group',
              'judgments': 'supplied by evaluators, not inferred or authenticated by this program',
              'groups': {}}
    for kind, participants in groups.items():
        total = len(participants)
        output = {'received_records': total, 'questions': []}
        for question in questions:
            positive, negative = ('correct', 'incorrect') if question['kind'] == 'fact' else ('supported', 'unsupported')
            counts = Counter(p[question['id']]['judgment'] if question['id'] in p else 'missing' for p in participants)
            output['questions'].append({**question,
                'counts': {key: counts[key] for key in (positive, negative, 'uncertain', 'missing')},
                'numerator': counts[positive], 'denominator': total,
                'rate': counts[positive] / total if total else None,
                'status': 'unmeasured' if not total else 'partial' if counts['missing'] else 'recorded'})
        report['groups'][kind] = output
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('feedback', type=Path)
    parser.add_argument('--text', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = json.loads(args.feedback.read_text(encoding='utf-8'))
        text = args.text.read_bytes().decode('utf-8')
        result = summarize(data, text)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
