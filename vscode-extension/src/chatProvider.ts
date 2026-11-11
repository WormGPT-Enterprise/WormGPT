import * as vscode from 'vscode';
import { config, getApiKey, toWireMessages } from './provider';
import { extractDelta, readSse } from './sse';

const MAX_INPUT_TOKENS = 128000;
const MAX_OUTPUT_TOKENS = 8192;

export class WormGptChatProvider implements vscode.LanguageModelChatProvider {
	constructor(private readonly ctx: vscode.ExtensionContext) {}

	private models(): vscode.LanguageModelChatInformation[] {
		const key = this.ctx.globalState.get<boolean>('hasApiKey', false);
		return config().models.map((id) => ({
			id,
			name: id,
			family: 'wormgpt',
			detail: key ? 'WormGPT' : 'WormGPT (API key required)',
			tooltip: `WormGPT model ${id}`,
			version: '1.0.0',
			maxInputTokens: MAX_INPUT_TOKENS,
			maxOutputTokens: MAX_OUTPUT_TOKENS,
			capabilities: {},
		}));
	}

	async provideLanguageModelChatInformation(): Promise<vscode.LanguageModelChatInformation[]> {
		return this.models();
	}

	async provideLanguageModelChatResponse(
		model: vscode.LanguageModelChatInformation,
		messages: readonly vscode.LanguageModelChatRequestMessage[],
		_options: vscode.ProvideLanguageModelChatResponseOptions,
		progress: vscode.Progress<vscode.LanguageModelResponsePart>,
		token: vscode.CancellationToken
	): Promise<void> {
		const apiKey = await getApiKey(this.ctx);
		if (!apiKey) {
			throw new Error('WormGPT API key is not set. Run "WormGPT: Set API Key".');
		}
		const { baseUrl } = config();
		const controller = new AbortController();
		const sub = token.onCancellationRequested(() => controller.abort());
		try {
			let response: Response;
			try {
				response = await fetch(`${baseUrl}/chat/completions`, {
					method: 'POST',
					headers: {
						'Content-Type': 'application/json',
						Authorization: `Bearer ${apiKey}`,
					},
					body: JSON.stringify({
						model: model.id,
						messages: toWireMessages(messages),
						stream: true,
					}),
					signal: controller.signal,
				});
			} catch (err) {
				if (controller.signal.aborted) {
					throw err;
				}
				const detail = err instanceof Error ? err.message : String(err);
				// A dead gateway host fails here as a DNS/connection error, never as an
				// HTTP status, so name the URL to make the cause obvious.
				throw new Error(
					`Cannot reach the WormGPT gateway at ${baseUrl}. ` +
					`Run "WormGPT: Set Gateway URL" and point it at your server. (${detail})`
				);
			}
			if (!response.ok || !response.body) {
				const detail = await response.text().catch(() => '');
				throw new Error(`WormGPT request failed (HTTP ${response.status}). ${detail.slice(0, 300)}`);
			}
			for await (const event of readSse(response.body)) {
				const text = extractDelta(event.data);
				if (text) {
					progress.report(new vscode.LanguageModelTextPart(text));
				}
			}
		} finally {
			sub.dispose();
		}
	}

	async provideTokenCount(
		_model: vscode.LanguageModelChatInformation,
		text: string | vscode.LanguageModelChatRequestMessage
	): Promise<number> {
		const raw = typeof text === 'string'
			? text
			: toWireMessages([text]).map((m) => m.content).join('');
		return Math.max(1, Math.ceil(raw.length / 4));
	}
}
