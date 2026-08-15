import http from 'node:http'

const port = Number(process.env.MOCK_API_PORT || 5174)

const json = (res, status, payload) => {
  res.writeHead(status, {
    'content-type': 'application/json',
    'access-control-allow-origin': '*',
    'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS',
    'access-control-allow-headers': 'content-type,authorization,x-active-tenant',
  })
  res.end(JSON.stringify(payload))
}

const ok = data => ({ success: true, message: 'ok', data })

const server = http.createServer((req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET,POST,PATCH,OPTIONS',
      'access-control-allow-headers': 'content-type,authorization,x-active-tenant',
    })
    res.end()
    return
  }

  const url = new URL(req.url ?? '/', `http://127.0.0.1:${port}`)
  if (url.pathname === '/api/app/config') {
    json(res, 200, ok({
      features: {
        worker_features_enabled: false,
        external_sharing_enabled: false,
        notebook_import_enabled: false,
        public_registration_enabled: false,
        local_auth_enabled: true,
        invitation_only: false,
        google_oauth_enabled: false,
        enterprise_licensed: false,
        team_sharing_enabled: false,
      },
      local_bootstrap: {
        user_id: '00000000-0000-0000-0000-000000000001',
        email: 'demo@local',
        full_name: 'Demo User',
        tenant_id: '00000000-0000-0000-0000-000000000001',
      },
    }))
    return
  }

  if (url.pathname === '/api/schedules') {
    json(res, 200, ok([]))
    return
  }

  if (url.pathname === '/api/scopes/all') {
    json(res, 200, ok({
      tenants: [{
        tenant_id: '00000000-0000-0000-0000-000000000001',
        tenant_name: 'Local Demo',
        role: 'owner',
        scopes: ['*'],
      }],
    }))
    return
  }

  if (url.pathname === '/api/tenants') {
    json(res, 200, ok([{ tenant_id: '00000000-0000-0000-0000-000000000001', tenant_name: 'Local Demo', role: 'owner', scopes: ['*'] }]))
    return
  }

  if (url.pathname === '/api/user-preferences') {
    json(res, 200, ok({}))
    return
  }

  if (url.pathname === '/api/connections' || url.pathname === '/api/datasources') {
    json(res, 200, ok({ items: [], total: 0 }))
    return
  }

  if (url.pathname === '/api/llm-connections') {
    json(res, 200, ok({ items: [], total: 0 }))
    return
  }

  if (url.pathname === '/api/llm-connections/models') {
    json(res, 200, { models_by_provider: { openai: ['gpt-4o-mini'] } })
    return
  }

  if (url.pathname === '/api/notebooks') {
    json(res, 200, ok({ items: [], total: 0 }))
    return
  }

  if (url.pathname === '/api/mcp/keys') {
    json(res, 200, ok([]))
    return
  }

  if (url.pathname === '/api/skill-suggestions/pending-count') {
    json(res, 200, ok(0))
    return
  }

  if (url.pathname.startsWith('/api/')) {
    json(res, 200, ok([]))
    return
  }

  json(res, 404, { success: false, message: 'not found' })
})

server.listen(port, '127.0.0.1', () => {
  console.log(`mock api listening on http://127.0.0.1:${port}`)
})

process.on('SIGTERM', () => server.close(() => process.exit(0)))
process.on('SIGINT', () => server.close(() => process.exit(0)))
