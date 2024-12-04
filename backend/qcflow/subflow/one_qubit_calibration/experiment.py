import abc
import time
from io import BytesIO

import matplotlib.pyplot as plt
from PIL import Image
from requests import get

from .util import TDM


def generate_dummy_figure(save_path: str, text):
    url = f"https://placehold.jp/3d4070/ffffff/100x50.png?text={text}"
    response = get(url)
    img = Image.open(BytesIO(response.content))
    fig, ax = plt.subplots()
    ax.imshow(img)
    ax.axis("off")
    plt.savefig(save_path, bbox_inches="tight")
    return fig


class IExperiment(metaclass=abc.ABCMeta):
    experiment_name: str
    input_parameters: list[str]
    output_parameters: list[str]

    def __init__(self, **kwargs: object):
        pass

    @abc.abstractmethod
    def take_data(self, tdm: TDM, notes: dict, save: bool) -> object:
        return object

    @abc.abstractmethod
    def analyze(self, dataset: object, notes: dict, savefig: bool, savepath: str):
        if savefig:
            for qubit_name in notes.keys():
                generate_dummy_figure(
                    f"{savepath}/{qubit_name}_{self.__class__.experiment_name}.png",
                    self.__class__.experiment_name,
                )
        pass


class Example1(IExperiment):
    experiment_name = "Example1"
    input_parameters = ["param1", "param2"]
    output_parameters = ["output1", "output2"]

    def take_data(self, tdm: TDM, notes: dict, save: bool) -> object:
        time.sleep(2)
        return object

    def analyze(self, dataset: object, notes: dict, savefig: bool, savepath: str):
        time.sleep(2)
        if savefig:
            for qubit_name in notes.keys():
                generate_dummy_figure(
                    f"{savepath}/{qubit_name}_{self.__class__.experiment_name}.png",
                    self.__class__.experiment_name,
                )
        pass


class Example2(IExperiment):
    experiment_name = "Example2"
    input_parameters = ["param1", "param2"]
    output_parameters = ["output1", "output2"]

    def take_data(self, tdm: TDM, notes: dict, save: bool) -> object:
        time.sleep(2)
        return object

    def analyze(self, dataset: object, notes: dict, savefig: bool, savepath: str):
        time.sleep(2)
        if savefig:
            for qubit_name in notes.keys():
                generate_dummy_figure(
                    f"{savepath}/{qubit_name}_{self.__class__.experiment_name}.png",
                    self.__class__.experiment_name,
                )
        pass


class Example3(IExperiment):
    experiment_name = "Example3"
    input_parameters = ["param1", "param2"]
    output_parameters = ["output1", "output2"]

    def take_data(self, tdm: TDM, notes: dict, save: bool) -> object:
        time.sleep(2)
        return object

    def analyze(self, dataset: object, notes: dict, savefig: bool, savepath: str):
        time.sleep(2)
        if savefig:
            for qubit_name in notes.keys():
                generate_dummy_figure(
                    f"{savepath}/{qubit_name}_{self.__class__.experiment_name}.png",
                    self.__class__.experiment_name,
                )
        pass


class Example4(IExperiment):
    experiment_name = "Example4"
    input_parameters = ["param1", "param2"]
    output_parameters = ["output1", "output2"]

    def take_data(self, tdm: TDM, notes: dict, save: bool) -> object:
        time.sleep(2)
        return object

    def analyze(self, dataset: object, notes: dict, savefig: bool, savepath: str):
        time.sleep(2)
        if savefig:
            for qubit_name in notes.keys():
                generate_dummy_figure(
                    f"{savepath}/{qubit_name}_{self.__class__.experiment_name}.png",
                    self.__class__.experiment_name,
                )
        pass


experiment_map = {
    "Example1": Example1(),
    "Example2": Example2(),
    "Example3": Example3(),
    "Example4": Example4(),
}
