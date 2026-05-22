import { describe, it, expect } from 'vitest';
import { citationGktuitionUrl, formatTimestamp } from '../src/utils/citations';

describe('citationGktuitionUrl', () => {
  it('builds the topic URL', () => {
    expect(
      citationGktuitionUrl({
        slug: 'the-line-4-area-of-triangle',
        title: 'The Line 4: Area',
        timestamp_seconds: null,
        score: 0.9,
      }),
    ).toBe('https://gktuition.ie/topic/the-line-4-area-of-triangle/');
  });

  it('appends ?t= when a timestamp is present', () => {
    expect(
      citationGktuitionUrl({
        slug: 'algebra-1-revision-of-jc-factorising',
        title: 'Factorising',
        timestamp_seconds: 142,
        score: 0.87,
      }),
    ).toBe('https://gktuition.ie/topic/algebra-1-revision-of-jc-factorising/?t=142');
  });

  it('omits ?t= when timestamp is zero', () => {
    expect(
      citationGktuitionUrl({
        slug: 'solutions-2024-p2-q5',
        title: 'Q5',
        timestamp_seconds: 0,
        score: 0.93,
      }),
    ).toBe('https://gktuition.ie/topic/solutions-2024-p2-q5/');
  });

  it('encodes slugs safely', () => {
    expect(
      citationGktuitionUrl({
        slug: 'foo bar',
        title: 'Foo',
        timestamp_seconds: null,
        score: 0.5,
      }),
    ).toBe('https://gktuition.ie/topic/foo%20bar/');
  });
});

describe('formatTimestamp', () => {
  it('formats < 1 hour as m:ss', () => {
    expect(formatTimestamp(0)).toBe('0:00');
    expect(formatTimestamp(5)).toBe('0:05');
    expect(formatTimestamp(65)).toBe('1:05');
    expect(formatTimestamp(599)).toBe('9:59');
  });

  it('formats >= 1 hour as h:mm:ss', () => {
    expect(formatTimestamp(3600)).toBe('1:00:00');
    expect(formatTimestamp(3725)).toBe('1:02:05');
  });

  it('returns empty for null/undefined/negative', () => {
    expect(formatTimestamp(null)).toBe('');
    expect(formatTimestamp(undefined)).toBe('');
    expect(formatTimestamp(-1)).toBe('');
  });
});
