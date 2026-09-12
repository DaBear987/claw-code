from pathlib import Path
import subprocess

path = Path('rust/crates/rusty-claude-cli/src/main.rs')
text = path.read_text()

if 'fn explicit_provider_kind_for_model(' in text:
    print('Provider precedence fix already present.')
    raise SystemExit(0)

marker = 'struct AnthropicRuntimeClient {'
helper = '''fn explicit_provider_kind_for_model(\n    model: &str,\n    persisted_model: &str,\n) -> Option<api::ProviderConfigKind> {\n    let resolved_model = api::resolve_model_alias(model);\n    let persisted_resolved = api::resolve_model_alias(persisted_model);\n\n    if resolved_model.eq_ignore_ascii_case(&persisted_resolved) {\n        return None;\n    }\n\n    let namespace = model\n        .trim()\n        .split_once('/')\n        .map(|(namespace, _)| namespace.to_ascii_lowercase());\n\n    match namespace.as_deref() {\n        Some("anthropic") => Some(api::ProviderConfigKind::Anthropic),\n        Some("xai") => Some(api::ProviderConfigKind::Xai),\n        Some("openai") | Some("local") => Some(api::ProviderConfigKind::OpenAi),\n        Some("dashscope") | Some("qwen") | Some("kimi") => {\n            Some(api::ProviderConfigKind::DashScope)\n        }\n        _ => {\n            let lower = resolved_model.to_ascii_lowercase();\n            if lower.starts_with("qwen/") || lower.starts_with("qwen-")\n                || lower.starts_with("kimi/") || lower.starts_with("kimi-")\n            {\n                Some(api::ProviderConfigKind::DashScope)\n            } else if lower.starts_with("grok/") || lower.starts_with("grok-") {\n                Some(api::ProviderConfigKind::Xai)\n            } else if lower.starts_with("claude") || lower.starts_with("anthropic/") {\n                Some(api::ProviderConfigKind::Anthropic)\n            } else if lower.starts_with("openai/") || lower.starts_with("gpt-")\n                || lower.starts_with("local/")\n            {\n                Some(api::ProviderConfigKind::OpenAi)\n            } else {\n                None\n            }\n        }\n    }\n}\n\n'''

if marker not in text:
    raise SystemExit('provider client anchor missing')
text = text.replace(marker, helper + marker, 1)

old = '''        let resolved_model = api::resolve_model_alias(&model);\n        let client = if let Some(config) = provider_config {'''
new = '''        let resolved_model = api::resolve_model_alias(&model);\n        let provider_config = provider_config.map(|config| {\n            if let Some(kind) =\n                explicit_provider_kind_for_model(&model, config.model.as_str())\n            {\n                api::ProviderConfig {\n                    kind,\n                    model: resolved_model.clone(),\n                    ..config\n                }\n            } else {\n                config\n            }\n        });\n        let client = if let Some(config) = provider_config {'''

if old not in text:
    raise SystemExit('runtime provider construction anchor missing')
text = text.replace(old, new, 1)

test_marker = '''    #[test]\n    fn persisted_provider_configuration_controls_runtime_provider_dispatch() {'''
test = '''    #[test]\n    fn explicit_model_provider_hint_overrides_persisted_provider_kind() {\n        let config = api::ProviderConfig {\n            kind: api::ProviderConfigKind::DashScope,\n            model: "qwen-plus".to_string(),\n            api_key: Some("persisted-test-key".to_string()),\n            base_url: None,\n        };\n\n        assert_eq!(\n            super::explicit_provider_kind_for_model("openai/gpt-5", &config.model),\n            Some(api::ProviderConfigKind::OpenAi)\n        );\n        assert_eq!(\n            super::explicit_provider_kind_for_model("qwen-plus", &config.model),\n            None,\n            "matching persisted model must keep the persisted provider kind"\n        );\n    }\n\n    #[test]\n    fn explicit_model_provider_hint_controls_runtime_provider_dispatch() {\n        let config = api::ProviderConfig {\n            kind: api::ProviderConfigKind::DashScope,\n            model: "qwen-plus".to_string(),\n            api_key: Some("persisted-test-key".to_string()),\n            base_url: None,\n        };\n\n        let runtime = super::AnthropicRuntimeClient::new(\n            "provider-resolution-explicit-model-test",\n            "openai/gpt-5".to_string(),\n            false,\n            false,\n            None,\n            GlobalToolRegistry::builtin(),\n            None,\n            Some(config),\n        )\n        .expect("runtime client should construct from explicit model provider hint");\n\n        match runtime.client {\n            api::ProviderClient::OpenAi(client) => {\n                assert!(client.base_url().contains("api.openai.com"));\n                assert!(!client.base_url().contains("dashscope.aliyuncs.com"));\n            }\n            other => panic!(\n                "explicit OpenAI model prefix must override persisted DashScope configuration, got {other:?}"\n            ),\n        }\n    }\n\n'''

if test_marker not in text:
    raise SystemExit('runtime precedence test anchor missing')
text = text.replace(test_marker, test + test_marker, 1)
path.write_text(text)
subprocess.run(['cargo', 'fmt', '--all'], cwd='rust', check=True)
