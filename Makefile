.PHONY: install test backtest compare pra pa screen fetch clean

install:
	python -m pip install -r requirements.txt

test:
	python -m unittest discover -s tests -v

backtest:
	python scripts/run_backtest.py --strategies protocol

compare:
	python scripts/run_backtest.py --strategies all --capital 1000

pra:
	python scripts/pra_study.py

pa:
	python scripts/pa_study.py

screen:
	python scripts/screen_candidates.py

fetch:
	python scripts/fetch_data.py --source nifty500 --start 2018-01-01 --limit 500

clean:
	rm -rf reports .protocol_state.json
