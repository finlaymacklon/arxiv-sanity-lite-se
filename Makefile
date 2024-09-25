
# I run this to update the database with newest papers every day or so or etc.
update:
	python3 arxiv_daemon.py --num 2000

# I use this to run the server
run:
	export FLASK_APP=serve.py; flask run
