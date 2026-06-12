from dayzops.cli import main

if __name__ == "__main__":
    # Propaga o código de retorno de main() como exit code do processo.
    # Sem isso, `python -m dayzops` sempre sairia 0 (mascarando falhas
    # de validate-config em scripts/CI).
    raise SystemExit(main())
