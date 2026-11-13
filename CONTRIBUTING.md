# Contribuindo com o Babel

Use Python 3.11 ou superior. Clone o projeto, crie um ambiente virtual e execute:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m babel_agent
```

O backend e o frontend não têm dependências de execução externas. Mantenha a instalação simples.
Para adicionar uma ferramenta, declare seu esquema em `babel_agent/tools.py`, implemente a execução e adicione testes. Toda ferramenta que altera arquivos deve entrar em `WRITES` e passar pelo fluxo de aprovação.

Pull requests devem explicar o problema, a mudança e como ela foi validada. Nunca inclua conversas, bancos de dados, arquivos pessoais ou credenciais. Testes automatizados usam modelos simulados; documente separadamente qualquer teste com um modelo real.
