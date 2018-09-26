
import tensorflow as tf

from .mac_cell import *
from ..util import *


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def expand_if_needed(t, target=4):
	if t is None:
		return t

	while len(t.shape) < target:
		t = tf.expand_dims(t, -1)
	return t


# --------------------------------------------------------------------------
# RNN loops
# --------------------------------------------------------------------------

def dynamic_decode(args, features, inputs, question_state, question_tokens, labels, vocab_embedding):
	with tf.variable_scope("decoder", reuse=tf.AUTO_REUSE) as decoder_scope:

		d_cell = MACCell(args, features, question_state, question_tokens, vocab_embedding)
		d_cell_initial = d_cell.zero_state(dtype=tf.float32, batch_size=features["d_batch_size"])
		
		# --------------------------------------------------------------------------
		# Decoding handlers
		# --------------------------------------------------------------------------

		finished_shape = tf.convert_to_tensor([features["d_batch_size"], 1])

		initialize_fn = lambda: (
			tf.fill(value=False, dims=finished_shape), # finished
			inputs[0],  # inputs
		)

		sample_fn = lambda time, outputs, state: tf.constant(0) # sampled output

		def next_inputs_fn(time, outputs, state, sample_ids):
			finished = tf.cast(outputs[1], tf.bool)
			next_inputs = tf.gather(inputs, time)
			next_state = state
			return (finished, next_inputs, next_state)

		decoder_helper = tf.contrib.seq2seq.CustomHelper(
			initialize_fn, sample_fn, next_inputs_fn
		)

		decoder = tf.contrib.seq2seq.BasicDecoder(
			d_cell,
			decoder_helper,
			d_cell_initial)


		# --------------------------------------------------------------------------
		# Do the decode!
		# --------------------------------------------------------------------------

		# 'outputs' is a tensor of shape [batch_size, max_time, cell.output_size]
		decoded_outputs, decoded_state, decoded_sequence_lengths = tf.contrib.seq2seq.dynamic_decode(
			decoder,
			swap_memory=True,
			maximum_iterations=args["max_decode_iterations"],
			scope=decoder_scope)

		out_taps = {
			key: decoded_outputs.rnn_output[idx+1]
			for idx, key in enumerate(d_cell.get_taps().keys())
		}
		
		# Take the final reasoning step output
		final_output = decoded_outputs.rnn_output[0][:,-1,:]
		
		return final_output, out_taps





def static_decode(args, features, inputs, question_state, question_tokens, labels, vocab_embedding):
	with tf.variable_scope("decoder", reuse=tf.AUTO_REUSE):

		d_cell = MACCell(args, features, question_state, question_tokens, vocab_embedding)
		d_cell_initial = d_cell.zero_state(dtype=tf.float32, batch_size=features["d_batch_size"])

		# Hard-coded unroll of the reasoning network for simplicity
		states = [(None, d_cell_initial)]
		for i in range(args["max_decode_iterations"]):
			with tf.variable_scope("decoder_cell", reuse=tf.AUTO_REUSE):
				states.append(d_cell(inputs[i], states[-1][1]))

		final_output = states[-1][0][0]

		def get_tap(idx, key):
			with tf.name_scope(f"get_tap_{key}"):
				tap = [i[0][idx] for i in states if i[0] is not None]
				for i in tap:
					if i is None:
						return None

				tap = tf.convert_to_tensor(tap)

				 # Deal with batch vs iteration axis layout
				if len(tap.shape) == 3:
					tap = tf.transpose(tap, [1,0,2]) # => batch, iteration, data
				if len(tap.shape) == 4:
					tap = tf.transpose(tap, [2,0,1,3]) # => batch, iteration, control_head, data
					
				return tap

		out_taps = {
			key: get_tap(idx+1, key)
			for idx, key in enumerate(d_cell.get_taps().keys())
		}
		
		return final_output, out_taps


def execute_reasoning(args, features, question_state, question_tokens, **kwargs):

	inputs = [
		tf.layers.dense(question_state, args["control_width"], name=f"question_state_inputs_t{i}") 
		for i in range(args["max_decode_iterations"])
	]

	if args["use_dynamic_decode"]:
		final_output, out_taps = dynamic_decode(args, features, inputs, question_state, question_tokens, **kwargs)
	else:
		final_output, out_taps = static_decode(args, features, inputs, question_state, question_tokens, **kwargs)

	final_output = dynamic_assert_shape(final_output, [features["d_batch_size"], args["output_classes"]])
	
	return final_output, out_taps




