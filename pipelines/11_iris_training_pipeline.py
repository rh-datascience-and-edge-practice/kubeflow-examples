"""
Example of a pipeline to demonstrate a simple real world data science workflow.
"""
import os

from dotenv import load_dotenv

from kfp import dsl
import kfp.compiler

import pandas as pd

load_dotenv(override=True)

kubeflow_endpoint = os.environ["KUBEFLOW_ENDPOINT"]
bearer_token = os.environ["BEARER_TOKEN"]

@dsl.component(
    base_image="image-registry.openshift-image-registry.svc:5000/openshift/python:latest",
    packages_to_install=["pandas", "scikit-learn"],
)
def data_prep(
    X_train_file: dsl.Output[dsl.Dataset],
    X_test_file: dsl.Output[dsl.Dataset],
    y_train_file: dsl.Output[dsl.Dataset],
    y_test_file: dsl.Output[dsl.Dataset],
):
    import pickle

    import pandas as pd

    from sklearn import datasets
    from sklearn.model_selection import train_test_split

    def get_iris_data() -> pd.DataFrame:
        iris = datasets.load_iris()
        data = pd.DataFrame(
            {
                "sepalLength": iris.data[:, 0],
                "sepalWidth": iris.data[:, 1],
                "petalLength": iris.data[:, 2],
                "petalWidth": iris.data[:, 3],
                "species": iris.target,
            }
        )

        print("Initial Dataset:")
        print(data.head())

        return data

    def create_training_set(dataset: pd.DataFrame, test_size: float = 0.3):
        # Features
        X = dataset[["sepalLength", "sepalWidth", "petalLength", "petalWidth"]]
        # Labels
        y = dataset["species"]

        # Split dataset into training set and test set
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=11
        )

        return X_train, X_test, y_train, y_test

    def save_pickle(object_file, target_object):
        with open(object_file, "wb") as f:
            pickle.dump(target_object, f)

    dataset = get_iris_data()
    X_train, X_test, y_train, y_test = create_training_set(dataset)

    save_pickle(X_train_file.path, X_train)
    save_pickle(X_test_file.path, X_test)
    save_pickle(y_train_file.path, y_train)
    save_pickle(y_test_file.path, y_test)

@dsl.component(
    base_image="image-registry.openshift-image-registry.svc:5000/openshift/python:latest",
    packages_to_install=["pandas", "scikit-learn"],
)
def validate_data():
    pass

@dsl.component(
    base_image="image-registry.openshift-image-registry.svc:5000/openshift/python:latest",
    packages_to_install=["pandas", "scikit-learn"],
)
def train_model(
    X_train_file: dsl.Input[dsl.Dataset],
    y_train_file: dsl.Input[dsl.Dataset],
    model_file: dsl.Output[dsl.Model],
):
    import pickle

    from sklearn.ensemble import RandomForestClassifier

    import pandas as pd

    def load_pickle(object_file):
        with open(object_file, "rb") as f:
            target_object = pickle.load(f)

        return target_object

    def save_pickle(object_file, target_object):
        with open(object_file, "wb") as f:
            pickle.dump(target_object, f)

    def train_iris(X_train: pd.DataFrame, y_train: pd.DataFrame):
        model = RandomForestClassifier(n_estimators=100)
        model.fit(X_train, y_train)

        return model

    X_train = load_pickle(X_train_file.path)
    y_train = load_pickle(y_train_file.path)

    model = train_iris(X_train, y_train)

    save_pickle(model_file.path, model)

@dsl.component(
    base_image="image-registry.openshift-image-registry.svc:5000/openshift/python:latest",
    packages_to_install=["pandas", "scikit-learn"],
)
def validate_model(model_file: dsl.Input[dsl.Model]):
    import pickle

    def load_pickle(object_file):
        with open(object_file, "rb") as f:
            target_object = pickle.load(f)

        return target_object

    model = load_pickle(model_file.path)

    input_values = [[5, 3, 1.6, 0.2]]

    print(f"Performing test prediction on {input_values}")
    result = model.predict(input_values)

    print(f"Response: {result}")

@dsl.component(
    base_image="image-registry.openshift-image-registry.svc:5000/openshift/python:latest",
    packages_to_install=["pandas", "scikit-learn"],
)
def evaluate_model(
    X_test_file: dsl.Input[dsl.Dataset],
    y_test_file:dsl.Input[dsl.Dataset],
    model_file: dsl.Input[dsl.Model],
    mlpipeline_metrics_file: dsl.Output[dsl.Metrics],
):
    import json
    import pickle

    from sklearn.metrics import accuracy_score

    def load_pickle(object_file):
        with open(object_file, "rb") as f:
            target_object = pickle.load(f)

        return target_object

    X_test = load_pickle(X_test_file.path)
    y_test = load_pickle(y_test_file.path)
    model = load_pickle(model_file.path)

    y_pred = model.predict(X_test)

    accuracy_score_metric = accuracy_score(y_test, y_pred)
    print(f"Accuracy: {accuracy_score_metric}")

    metrics = {
        "metrics": [
            {
                "name": "accuracy-score",
                "numberValue": accuracy_score_metric,
                "format": "PERCENTAGE",
            },
        ]
    }

    with open(mlpipeline_metrics_file.path, "w") as f:
        json.dump(metrics, f)


@kfp.dsl.pipeline(
    name="Iris Pipeline",
)
def iris_pipeline(model_obc: str = "iris-model"):
    data_prep_task = data_prep()

    train_model_task = train_model(
        X_train_file = data_prep_task.outputs["X_train_file"],
        y_train_file = data_prep_task.outputs["y_train_file"],
    )

    evaluate_model_task = evaluate_model(  # noqa: F841
        X_test_file = data_prep_task.outputs["X_test_file"],
        y_test_file = data_prep_task.outputs["y_test_file"],
        model_file = train_model_task.output,
    )

    validate_model_task = validate_model(model_file = train_model_task.output)  # noqa: F841


if __name__ == "__main__":
    print(f"Connecting to kfp: {kubeflow_endpoint}")
    client = kfp.Client(
        host=kubeflow_endpoint,
        existing_token=bearer_token,
    )
    result = client.create_run_from_pipeline_func(
        iris_pipeline, arguments={}, experiment_name="iris"
    )
    print(f"Starting pipeline run with run_id: {result.run_id}")
