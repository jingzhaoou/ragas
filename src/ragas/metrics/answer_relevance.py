from __future__ import annotations

import typing as t
from dataclasses import dataclass

import numpy as np
from datasets import Dataset
from langchain.embeddings import OpenAIEmbeddings
from langchain.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from tqdm import tqdm

from ragas.metrics.base import EvaluationMode, MetricWithLLM
from ragas.metrics.llms import generate

if t.TYPE_CHECKING:
    pass


QUESTION_GEN = HumanMessagePromptTemplate.from_template(
    """
Generate question for the given answer.
Answer:\nThe PSLV-C56 mission is scheduled to be launched on Sunday, 30 July 2023 at 06:30 IST / 01:00 UTC. It will be launched from the Satish Dhawan Space Centre, Sriharikota, Andhra Pradesh, India 
Question: When is the scheduled launch date and time for the PSLV-C56 mission, and where will it be launched from?

Answer:{answer}
Question:
"""  # noqa: E501
)


@dataclass
class AnswerRelevancy(MetricWithLLM):
    """
    Scores the relevancy of the answer according to the given question.
    Answers with incomplete, redundant or unnecessary information is penalized.
    Score can range from 0 to 1 with 1 being the best.

    Attributes
    ----------
    name: string
        The name of the metrics
    batch_size: int
        batch size for evaluation
    strictness: int
        Here indicates the number questions generated per answer.
        Ideal range between 3 to 5.
    """

    name: str = "answer_relevancy"
    evaluation_mode: EvaluationMode = EvaluationMode.qa
    batch_size: int = 15
    strictness: int = 3

    def init_model(self: t.Self):
        self.embedding = OpenAIEmbeddings()  # type: ignore

    def score(self: t.Self, dataset: Dataset) -> Dataset:
        scores = []
        for batch in tqdm(self.get_batches(len(dataset))):
            score = self._score_batch(dataset.select(batch))
            scores.extend(score)

        return dataset.add_column(f"{self.name}", scores)  # type: ignore

    def _score_batch(self: t.Self, dataset: Dataset):
        questions, answers = dataset["question"], dataset["answer"]

        prompts = []
        for ans in answers:
            human_prompt = QUESTION_GEN.format(answer=ans)
            prompts.append(ChatPromptTemplate.from_messages([human_prompt]))

        results = generate(prompts, self.llm, n=self.strictness)
        results = [[i.text for i in r] for r in results.generations]

        scores = []
        for question, gen_questions in zip(questions, results):
            cosine_sim = self.calculate_similarity(question, gen_questions)
            scores.append(cosine_sim.max())

        return scores

    def calculate_similarity(
        self: t.Self, question: str, generated_questions: list[str]
    ):
        question_vec = np.asarray(self.embedding.embed_query(question)).reshape(1, -1)
        gen_question_vec = np.asarray(
            self.embedding.embed_documents(generated_questions)
        )
        norm = np.linalg.norm(gen_question_vec, axis=1) * np.linalg.norm(
            question_vec, axis=1
        )
        return (
            np.dot(gen_question_vec, question_vec.T).reshape(
                -1,
            )
            / norm
        )


answer_relevancy = AnswerRelevancy()