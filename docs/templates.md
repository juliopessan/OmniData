# WhatsApp templates to submit (utility, pt_BR)
| Name | Body | Quick-reply button |
|---|---|---|
| `onboarding_v1` | Olá, {{1}}! Sou o assistente de vendas da sua empresa. Para ativar, responda *Aceito*. Vou usar seus dados de vendas do HubSpot para ajudar você. | Aceito |
| `morning_brief_v1` | Bom dia, {{1}}! Você tem {{2}} negócios prioritários hoje. | Ver meu dia |
| `alert_deal_v1` | Atenção: *{{1}}* {{2}}. | Ver deal |
| `loss_reason_v1` (M2) | O negócio *{{1}}* foi perdido. Qual foi o motivo? | Responder |
| `weekly_review_v1` (P1) | Sua semana, {{1}}: resumo pronto. | Ver semana |
The quick-reply payloads the code sends are `aceito`, `act:open:brief` and `act:open:<alert_event_id>`.
