import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  MemoryRouter,
  Outlet,
  Route,
  Routes,
} from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { WorkbenchLayout } from '@/components/layout/WorkbenchLayout'

describe('WorkbenchLayout', () => {
  it('clips horizontal overflow on narrow workbench viewports', () => {
    const html = renderToStaticMarkup(
      createElement(
        MemoryRouter,
        { initialEntries: ['/workbench'] },
        createElement(
          Routes,
          null,
          createElement(
            Route,
            { element: createElement(WorkbenchLayout) },
            createElement(Route, {
              path: '/workbench',
              element: createElement(Outlet),
            }),
          ),
        ),
      ),
    )

    expect(html).toContain('overflow-x-hidden')
  })
})
