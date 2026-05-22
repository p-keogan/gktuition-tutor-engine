/**
 * Unit tests for the PlotlyGraph component.
 *
 * We don't load the real Plotly CDN script in jsdom; instead we stub
 * `window.Plotly` with a tiny fake that records calls so we can assert
 * the component passes the right `data` + `layout` and renders the
 * accessibility summary correctly.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, test, vi } from 'vitest';
import { PlotlyGraph } from '../src/components/PlotlyGraph';
import { MessageBubble } from '../src/components/MessageBubble';
import type { GraphSpec } from '../src/api/types';

const SIN_FIGURE: GraphSpec = {
  kind: 'trig',
  figure: {
    data: [
      {
        type: 'scatter',
        mode: 'lines',
        name: 'sin',
        x: [0, 1, 2, 3],
        y: [0, 0.84, 0.91, 0.14],
      },
    ],
    layout: {
      title: { text: 'y = sin(x)' },
      xaxis: { title: 'x' },
      yaxis: { title: 'y' },
      meta: { summary: 'Sine curve with amplitude 1' },
    },
  },
};

const POLY_FIGURE: GraphSpec = {
  kind: 'polynomial',
  figure: {
    data: [
      {
        type: 'scatter',
        mode: 'lines',
        name: 'f(x)',
        x: [-2, -1, 0, 1, 2],
        y: [0, -3, -4, -3, 0],
      },
    ],
    layout: {
      title: { text: 'f(x) = x² − 4' },
      xaxis: { title: 'x' },
      yaxis: { title: 'y' },
      meta: { summary: 'Polynomial of degree 2 plotted over [-5, 5]' },
    },
  },
};

describe('PlotlyGraph', () => {
  beforeEach(() => {
    // Reset the module-level loader between tests by reaching at the window
    // global; the component reuses any pre-attached `window.Plotly`.
    const fakePlotly = {
      newPlot: vi.fn().mockResolvedValue(undefined),
      purge: vi.fn(),
      Plots: { resize: vi.fn() },
    };
    (window as unknown as { Plotly: typeof fakePlotly }).Plotly = fakePlotly;
  });

  test('renders a container with the right kind data attribute', () => {
    render(<PlotlyGraph spec={SIN_FIGURE} index={0} />);
    const container = screen.getByTestId('gktuition-graph-0');
    expect(container).toBeInTheDocument();
    expect(container.getAttribute('data-kind')).toBe('trig');
  });

  test('passes accessibility summary to aria-label', () => {
    render(<PlotlyGraph spec={POLY_FIGURE} index={1} />);
    const canvas = screen.getByRole('img');
    expect(canvas.getAttribute('aria-label')).toContain('Polynomial of degree 2');
  });

  test('invokes window.Plotly.newPlot with the data + layout', async () => {
    render(<PlotlyGraph spec={POLY_FIGURE} index={0} />);
    await waitFor(() => {
      const plotly = (window as unknown as { Plotly: { newPlot: ReturnType<typeof vi.fn> } })
        .Plotly;
      expect(plotly.newPlot).toHaveBeenCalled();
    });
    const plotly = (window as unknown as { Plotly: { newPlot: ReturnType<typeof vi.fn> } })
      .Plotly;
    const call = plotly.newPlot.mock.calls[0];
    expect(call[1]).toEqual(POLY_FIGURE.figure.data);
  });

  test('expand button toggles the expanded class', async () => {
    render(<PlotlyGraph spec={SIN_FIGURE} index={0} />);
    const container = screen.getByTestId('gktuition-graph-0');
    expect(container.className).not.toContain('expanded');
    const btn = screen.getByRole('button', { name: /expand graph/i });
    await userEvent.click(btn);
    expect(container.className).toContain('gktuition-tutor__graph--expanded');
  });
});

describe('MessageBubble — graphs wiring', () => {
  beforeEach(() => {
    const fakePlotly = {
      newPlot: vi.fn().mockResolvedValue(undefined),
      purge: vi.fn(),
      Plots: { resize: vi.fn() },
    };
    (window as unknown as { Plotly: typeof fakePlotly }).Plotly = fakePlotly;
  });

  test('renders one PlotlyGraph per graph in the assistant message', () => {
    render(
      <MessageBubble
        message={{
          id: 'm1',
          role: 'assistant',
          text: 'Here is the sketch.',
          graphs: [SIN_FIGURE, POLY_FIGURE],
        }}
      />,
    );
    expect(screen.getByTestId('gktuition-graph-0')).toBeInTheDocument();
    expect(screen.getByTestId('gktuition-graph-1')).toBeInTheDocument();
  });

  test('renders no graph container when graphs is absent', () => {
    render(
      <MessageBubble
        message={{
          id: 'm1',
          role: 'assistant',
          text: 'Just text.',
        }}
      />,
    );
    expect(screen.queryByTestId('gktuition-graph-0')).not.toBeInTheDocument();
  });

  test('does not render graphs on a user-role message even if present', () => {
    render(
      <MessageBubble
        message={{
          id: 'm1',
          role: 'user',
          text: 'Sketch y=sin(x)',
          graphs: [SIN_FIGURE],
        }}
      />,
    );
    expect(screen.queryByTestId('gktuition-graph-0')).not.toBeInTheDocument();
  });
});
