import * as vscode from 'vscode';

export const VENDOR = 'wormgpt';

export interface WireMessage {
	role: 'system' | 'user' | 'assistant';
	content: string;
}

export function config() {
	const cfg = vscode.workspace.getConfiguration('wormgpt');
	return {
		baseUrl: String(cfg.get('baseUrl') || 'https://api.wormgpt.live/v1').replace(/\/+$/, ''),
		models: (cfg.get<string[]>('models') || []).filter(Boolean),
	};
}

export async function getApiKey(ctx: vscode.ExtensionContext): Promise<string> {
	return (await ctx.secrets.get('wormgpt.apiKey')) || '';
}

export async function setApiKey(ctx: vscode.ExtensionContext, key: string): Promise<void> {
	await ctx.secrets.store('wormgpt.apiKey', key.trim());
}

export function toWireMessages(
	messages: readonly vscode.LanguageModelChatRequestMessage[]
): WireMessage[] {
	const out: WireMessage[] = [];
	for (const message of messages) {
		const text = message.content
			.map((part) => (part instanceof vscode.LanguageModelTextPart ? part.value : ''))
			.join('');
		if (!text) {
			continue;
		}
		out.push({
			role: message.role === vscode.LanguageModelChatMessageRole.Assistant ? 'assistant' : 'user',
			content: text,
		});
	}
	return out;
}
