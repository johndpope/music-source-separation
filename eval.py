# -*- coding: utf-8 -*-
# !/usr/bin/env python

import tensorflow as tf
from model import Model, load_state, batch_to_spec, spec_to_batch
import os
from data import Data
from preprocess import *
from config import EvalConfig
from mir_eval.separation import bss_eval_sources
import shutil


def eval():
    # Model
    model = Model()
    global_step = tf.Variable(0, dtype=tf.int32, trainable=False, name='global_step')

    with tf.Session(config=EvalConfig.session_conf) as sess:

        # Initialized, Load state
        sess.run(tf.global_variables_initializer())
        load_state(sess, EvalConfig.CKPT_PATH)

        writer = tf.summary.FileWriter(EvalConfig.GRAPH_PATH, sess.graph)

        data = Data(EvalConfig.DATA_PATH)
        mixed_wav, src1_wav, src2_wav = data.next_wavs(EvalConfig.NUM_EVAL, sec=EvalConfig.SECONDS)

        # TODO refactoring
        mixed_spec = to_spectrogram(mixed_wav)
        mixed_mag = get_magnitude(mixed_spec)
        mixed_phase = get_phase(mixed_spec)
        mixed_batched = spec_to_batch(mixed_mag)

        pred = sess.run(model(), feed_dict={model.x_mixed: mixed_batched})

        # (magnitude, phase) -> spectrogram -> wav
        pred_src1_mag, pred_src2_mag = pred
        pred_src1_mag = batch_to_spec(pred_src1_mag, EvalConfig.NUM_EVAL)
        pred_src2_mag = batch_to_spec(pred_src2_mag, EvalConfig.NUM_EVAL)
        mixed_phase = mixed_phase[:, :, :pred_src1_mag.shape[-1]]

        # Time-frequency masking
        # mask_src1 = time_freq_mask(pred_src1_mag, pred_src2_mag)
        # mask_src2 = 1.0 - mask_src1
        # seq_len = mixed_batched.shape[0] * mixed_batched.shape[1] // EvalConfig.NUM_EVAL
        # mixed_mag = mixed_mag[:, :, :seq_len]
        # pred_src1_mag = mixed_mag * mask_src1
        # pred_src2_mag = mixed_mag * mask_src2

        # (magnitude, phase) -> spectrogram -> wav
        pred_src1_spec = get_stft_matrix(pred_src1_mag, mixed_phase)
        pred_src2_spec = get_stft_matrix(pred_src2_mag, mixed_phase)
        pred_src1_wav, pred_src2_wav = to_wav(pred_src1_spec), to_wav(pred_src2_spec)

        # Write the result
        tf.summary.audio('GT_mixed', mixed_wav, ModelConfig.SR)
        tf.summary.audio('Pred_music', pred_src1_wav, ModelConfig.SR)
        tf.summary.audio('Pred_vocal', pred_src2_wav, ModelConfig.SR)

        # Compute BSS metrics
        gnsdr, gsir, gsar = bss_eval_global(mixed_wav, src1_wav, src2_wav, pred_src1_wav, pred_src2_wav)

        # Write the score of BSS metrics
        tf.summary.scalar('GNSDR_music', gnsdr[0])
        tf.summary.scalar('GSIR_music', gsir[0])
        tf.summary.scalar('GSAR_music', gsar[0])
        tf.summary.scalar('GNSDR_vocal', gnsdr[1])
        tf.summary.scalar('GSIR_vocal', gsir[1])
        tf.summary.scalar('GSAR_vocal', gsar[1])

        writer.add_summary(sess.run(tf.summary.merge_all()), global_step=global_step.eval())

        writer.close()


def bss_eval_global(mixed_wav, src1_wav, src2_wav, pred_src1_wav, pred_src2_wav):
    len_cropped = pred_src1_wav.shape[-1]
    src1_wav = src1_wav[:, :len_cropped]
    src2_wav = src2_wav[:, :len_cropped]
    mixed_wav = mixed_wav[:, :len_cropped]
    gnsdr, gsir, gsar = np.zeros(2), np.zeros(2), np.zeros(2)
    total_len = 0
    for i in range(EvalConfig.NUM_EVAL):
        sdr, sir, sar, _ = bss_eval_sources(np.array([src1_wav[i], src2_wav[i]]),
                                            np.array([pred_src1_wav[i], pred_src2_wav[i]]), False)
        sdr_mixed, _, _, _ = bss_eval_sources(np.array([src1_wav[i], src2_wav[i]]),
                                              np.array([mixed_wav[i], mixed_wav[i]]), False)
        nsdr = sdr - sdr_mixed
        gnsdr += len_cropped * nsdr
        gsir += len_cropped * sir
        gsar += len_cropped * sar
        total_len += len_cropped
    gnsdr = gnsdr / total_len
    gsir = gsir / total_len
    gsar = gsar / total_len
    return gnsdr, gsir, gsar


def setup_path():
    if EvalConfig.RE_EVAL:
        if os.path.exists(EvalConfig.GRAPH_PATH):
            shutil.rmtree(EvalConfig.GRAPH_PATH)

    if not os.path.exists(EvalConfig.RESULT_PATH):
        os.makedirs(EvalConfig.RESULT_PATH)


if __name__ == '__main__':
    setup_path()
    eval()
