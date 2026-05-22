/**
 * Citation click test — simulates a user clicking a citation chip and
 * verifies the right URL would be navigated to (we assert on the href +
 * the click event default behaviour rather than actually navigating,
 * since jsdom doesn't have a real browser).
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Citation } from '../src/components/Citation';

describe('Citation click', () => {
  it('renders a click-target whose href deep-links into the gktuition.ie topic page with timestamp', async () => {
    render(
      <Citation
        citation={{
          slug: 'algebra-1-revision-of-jc-factorising',
          title: 'Algebra 1 — Factorising',
          timestamp_seconds: 142,
          score: 0.87,
        }}
      />,
    );
    const link = screen.getByTestId('gktuition-citation');
    expect(link).toHaveAttribute(
      'href',
      'https://gktuition.ie/topic/algebra-1-revision-of-jc-factorising/?t=142',
    );
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('click does not throw and preserves the navigation intent', async () => {
    const user = userEvent.setup();
    render(
      <Citation
        citation={{
          slug: 'solutions-2024-p2-q5',
          title: '2024 P2 Q5',
          timestamp_seconds: 0,
          score: 0.91,
        }}
      />,
    );
    const link = screen.getByTestId('gktuition-citation');
    // jsdom: click works, default navigation is harmless. We assert the
    // href is what would be navigated to.
    await user.click(link);
    expect(link.getAttribute('href')).toBe('https://gktuition.ie/topic/solutions-2024-p2-q5/');
  });
});
