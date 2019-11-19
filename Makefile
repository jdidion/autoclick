package = autoclick
repo = jdidion/$(package)
version = 0.8.0
tests = tests
pytestopts = -s -vv --show-capture=all
desc = Release $(version)

all: clean install test

build: clean
	poetry build

lock:
	poetry lock

install: build
	pip install --upgrade dist/$(package)-$(version)-*.whl $(installargs)

install_test_deps:
	pip install -r requirements-test.txt

test: install_test_deps
	coverage run -m pytest $(pytestopts) $(tests)
	coverage report -m
	coverage xml

docs:
	make -C docs api
	make -C docs html

lint:
	flake8 $(package)

reformat:
	black $(package)
	black $(tests)

clean:
	rm -Rf __pycache__
	rm -Rf **/__pycache__/*
	rm -Rf **/*.so
	rm -Rf **/*.pyc
	rm -Rf dist
	rm -Rf build
	rm -Rf $(package).egg-info

docker:
	# build
	docker build -f Dockerfile -t $(repo):$(version) .
	# add alternate tags
	docker tag $(repo):$(version) $(repo):latest
	# push to Docker Hub
	# requires user to be logged in to account with
	# permissions to push to $(repo)
	docker push $(repo)

tag:
	git tag $(version)

push_tag:
	git push origin --tags

del_tag:
	git tag -d $(version)

set_version:
	poetry version $(dunamai from git --no-metadata --style semver)

pypi_release:
	poetry publish

release: clean tag
	${MAKE} install test pypi_release push_tag || (${MAKE} del_tag set_version && exit 1)

	# create release in GitHub
	curl -v -i -X POST \
		-H "Content-Type:application/json" \
		-H "Authorization: token $(token)" \
		https://api.github.com/repos/$(repo)/releases \
		-d '{"tag_name":"$(version)","target_commitish": "master","name": "$(version)","body": "$(desc)","draft": false,"prerelease": false}'
