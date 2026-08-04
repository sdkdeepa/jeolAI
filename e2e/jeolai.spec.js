import { expect, test } from '@playwright/test';

const normalTrace = {
  metrics: { models: ['gemini-2.5-flash-lite'], input_tokens: 312, output_tokens: 146, estimated_cost_usd: 0.000214, total_latency_ms: 824, tool_calls: 1, model_calls: 2 },
  budget: { dollars_spent: 0.000214, budget_cap: 0.1, percent_used: 0.214, tier: 'normal' },
  steps: [
    { step_type: 'request', label: 'Request received' },
    { step_type: 'guardrail', label: 'Domain guard passed' },
    { step_type: 'policy', label: 'Budget policy evaluated', details: { tier: 'normal' } },
    { step_type: 'model_call', label: 'Gemini model call: gemini-2.5-flash-lite', model: 'gemini-2.5-flash-lite', input_tokens: 312, output_tokens: 54, cost_usd: 0.000142, latency_ms: 510 },
    { step_type: 'tool_call', label: 'Executed tool: search_products', latency_ms: 18, details: { input: { query: 'waterproof hiking boots', max_price: 170 }, output: [{ name: 'Summit GTX Hiking Boots', price: 159 }] } },
    { step_type: 'response', label: 'Final response generated' },
  ],
};
const blockedTrace = { metrics: { models: [], input_tokens: 0, output_tokens: 0, estimated_cost_usd: 0, total_latency_ms: 4, tool_calls: 0, model_calls: 0 }, budget: { dollars_spent: 0, budget_cap: 0.1, percent_used: 0, tier: 'normal' }, steps: [{ step_type:'request', label:'Request received' }, { step_type:'blocked', label:'Domain guard rejected request' }, { step_type:'blocked', label:'Request stopped before model invocation' }] };

async function mockApi(page) {
  let trace = normalTrace;
  await page.route('http://127.0.0.1:8000/chat', async route => {
    const body = route.request().postDataJSON();
    const blocked = /reverse|string|kubernetes|poem/i.test(body.message);
    trace = blocked ? blockedTrace : normalTrace;
    await route.fulfill({ status:200, contentType:'application/json', body:JSON.stringify(blocked ? { reply:"I don't know. I can only help with shopping, products, promotions, inventory, carts, and checkout.", domain_allowed:false, requires_approval:false } : { reply:'I found Summit GTX Hiking Boots for $159.', domain_allowed:true, requires_approval:false }) });
  });
  await page.route(/http:\/\/127\.0\.0\.1:8000\/trace\/.+/, r => r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(trace)}));
  await page.route('http://127.0.0.1:8000/end-chat', r => r.fulfill({status:200,contentType:'application/json',body:JSON.stringify({total_messages:2,duration_seconds:42,total_tokens:458,estimated_cost_usd:0.000214,model_calls:2,tool_calls:1,total_latency_ms:824,current_budget_tier:'normal',transcript:[{role:'user',message:'Find waterproof hiking boots under $170.'},{role:'assistant',message:'I found Summit GTX Hiking Boots for $159.'}]})}));
  await page.route('http://127.0.0.1:8000/debug/set-spend', r => r.fulfill({status:200,contentType:'application/json',body:'{}'}));
  await page.route(/http:\/\/127\.0\.0\.1:8000\/session\/.+/, r => r.fulfill({status:200,contentType:'application/json',body:'{}'}));
}

test.beforeEach(async ({page}) => { await mockApi(page); await page.goto('/'); });

test('renders the React two-panel layout', async ({page}) => {
  await expect(page.getByRole('heading',{name:'Shopping conversation'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Agent execution'})).toBeVisible();
  const chat=await page.getByTestId('chat-card').boundingBox(); const exec=await page.getByTestId('execution-card').boundingBox();
  expect(exec.x).toBeGreaterThan(chat.x + chat.width - 10);
});

test('updates response and execution metrics', async ({page}) => {
  await page.getByPlaceholder(/Build me a hiking outfit/i).fill('Find waterproof hiking boots under $170.');
  await page.getByRole('button',{name:'Send'}).click();
  await expect(page.getByText('I found Summit GTX Hiking Boots for $159.')).toBeVisible();
  await expect(page.locator('[data-metric="model-selected"]')).toHaveText('gemini-2.5-flash-lite');
  await expect(page.locator('[data-metric="input-tokens"]')).toHaveText('312');
  await expect(page.locator('[data-metric="estimated-cost"]')).toHaveText('$0.000214');
  await expect(page.getByText('Executed tool: search_products')).toBeVisible();
});

test('blocks off-domain requests with zero model usage', async ({page}) => {
  await page.getByPlaceholder(/Build me a hiking outfit/i).fill('How do I reverse a string in Python?');
  await page.getByRole('button',{name:'Send'}).click();
  await expect(page.getByText(/I don't know. I can only help with shopping/)).toBeVisible();
  await expect(page.locator('[data-metric="model-selected"]')).toHaveText('Not called');
  await expect(page.locator('[data-metric="input-tokens"]')).toHaveText('0');
  await expect(page.locator('[data-metric="tool-calls"]')).toHaveText('0');
});

test('summary closes back to active chat', async ({page}) => {
  await page.getByRole('button',{name:'End chat'}).click();
  await expect(page.getByRole('heading',{name:'Session summary'})).toBeVisible();
  await page.getByRole('button',{name:'Close session summary'}).click();
  await expect(page.getByRole('heading',{name:'Session summary'})).toBeHidden();
  await expect(page.getByRole('button',{name:'End chat'})).toBeEnabled();
  await expect(page.getByPlaceholder(/Build me a hiking outfit/i)).toBeEnabled();
});

test('composer remains anchored inside the chat card', async ({page}) => {
  const input=page.getByPlaceholder(/Build me a hiking outfit/i);
  for(let i=0;i<5;i++){ await input.fill(`Find hiking boots ${i}`); await page.getByRole('button',{name:'Send'}).click(); }
  const card=await page.getByTestId('chat-card').boundingBox(); const composer=await page.getByTestId('composer').boundingBox();
  expect(composer.y + composer.height).toBeLessThanOrEqual(card.y + card.height + 2);
});
