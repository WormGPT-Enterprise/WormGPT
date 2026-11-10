export interface SseEvent {
data: string;
}

/**
 * Minimal Server-Sent Events reader over a fetch body. Yields the text
 * content of each `data:` line so the caller does not deal with framing.
 */
export async function* readSse(
body: ReadableStream<Uint8Array>
): AsyncGenerator<SseEvent> {
const reader = body.getReader();
const decoder = new TextDecoder();
let buffer = '';
for (;;) {
const { done, value } = await reader.read();
if (done) {
break;
}
buffer += decoder.decode(value, { stream: true });
let index: number;
while ((index = buffer.indexOf('\n')) !== -1) {
const line = buffer.slice(0, index).replace(/\r$/, '');
buffer = buffer.slice(index + 1);
if (line.startsWith('data:')) {
yield { data: line.slice(5).trim() };
}
}
}
}

export function extractDelta(data: string): string {
try {
const obj = JSON.parse(data);
const choice = obj && obj.choices && obj.choices[0];
const delta = choice && (choice.delta || choice.message);
return (delta && delta.content) || '';
} catch {
return '';
}
}
