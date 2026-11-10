import * as vscode from 'vscode';
import { WormGptChatProvider } from './chatProvider';
import { setApiKey, VENDOR } from './provider';

export function activate(ctx: vscode.ExtensionContext): void {
	const provider = new WormGptChatProvider(ctx);
	ctx.subscriptions.push(vscode.lm.registerLanguageModelChatProvider(VENDOR, provider));

	ctx.subscriptions.push(
		vscode.commands.registerCommand('wormgpt.setApiKey', async () => {
			const key = await vscode.window.showInputBox({
				title: 'WormGPT API Key',
				prompt: 'Paste a key created in the WormGPT API Platform (wrm_live_... or wrm_test_...).',
				password: true,
				ignoreFocusOut: true,
			});
			if (!key) {
				return;
			}
			await setApiKey(ctx, key);
			await ctx.globalState.update('hasApiKey', true);
			vscode.window.showInformationMessage('WormGPT API key saved.');
		})
	);

	ctx.subscriptions.push(
		vscode.commands.registerCommand('wormgpt.setBaseUrl', async () => {
			const current = vscode.workspace.getConfiguration('wormgpt').get<string>('baseUrl') || '';
			const url = await vscode.window.showInputBox({
				title: 'WormGPT Gateway URL',
				value: current,
				ignoreFocusOut: true,
			});
			if (url === undefined) {
				return;
			}
			await vscode.workspace
				.getConfiguration('wormgpt')
				.update('baseUrl', url, vscode.ConfigurationTarget.Global);
		})
	);
}

export function deactivate(): void {}
