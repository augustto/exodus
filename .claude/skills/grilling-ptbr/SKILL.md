---
name: grilling-ptbr
description: Questione o usuário de forma incisiva sobre um plano, decisão ou ideia. Use quando ele quiser explorar um assunto em profundidade, para que ambos cheguem a um entendimento comum.
---

<!-- Tradução pt-BR da skill original criada por Matt Pocock: https://github.com/mattpocock/skills/blob/main/skills/productivity/grilling/SKILL.md -->

Entreviste o usuário de forma incisiva até chegar a um entendimento comum. Mapeie o assunto como uma **árvore de decisões**: cada decisão se ramifica nas decisões que dependem dela.

Percorra a árvore **uma pergunta por vez**. A **fronteira** reúne todas as decisões cujos pré-requisitos já foram resolvidos: são as perguntas que você pode fazer _agora_ sem presumir respostas que ainda não recebeu. Escolha da fronteira a pergunta mais fundamental (a que libera mais decisões dependentes), faça apenas ela com sua resposta recomendada e aguarde a resposta do usuário antes de fazer a próxima. Numere as perguntas em sequência ao longo de toda a sessão (P1, P2, P3…).

Formate cada pergunta assim:

```
❓ **P<n>** - **<título da pergunta>**: <enunciado, que pode ter vários parágrafos e opções de resposta>

➡️ **R<n>** - <sua resposta recomendada>
```

Cada resposta do usuário remodela a árvore: a decisão resolvida amplia a fronteira e libera as perguntas que dependiam dela. Recalcule a fronteira e faça a próxima pergunta. Nunca pergunte algo cuja resposta dependa de uma decisão ainda em aberto.

Apurar _fatos_ é sua responsabilidade, nunca a do usuário. Quando uma pergunta da fronteira exigir um fato do ambiente (sistema de arquivos, ferramentas etc.), encarregue um subagente de encontrá-lo; não peça ao usuário informações que você mesmo possa consultar. Não trave a sessão por isso: uma investigação em andamento é um pré-requisito ainda não resolvido, então apenas as perguntas que dependem dela devem esperar o retorno do subagente. Enquanto isso, faça a próxima pergunta da fronteira que não dependa dela. As _decisões_ cabem ao usuário: apresente cada uma e aguarde sua resposta.

A sessão termina quando a fronteira estiver vazia: todos os ramos da árvore de decisões foram percorridos e nada ficou implicitamente presumido. Não execute o plano até que o usuário confirme que vocês chegaram a um entendimento comum.
