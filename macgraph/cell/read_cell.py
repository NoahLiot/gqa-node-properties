
import tensorflow as tf

from ..util import *
from ..attention import *
from ..input import UNK_ID, get_table_with_embedding
from ..args import ACTIVATION_FNS


def read_from_table(args, features, in_signal, noun, table, width, keys_len=None):

	query = tf.layers.dense(in_signal, width)

	output, score_sm, total_raw_score = attention(table, query,
		key_width=width, 
		keys_len=keys_len,
	)

	output = dynamic_assert_shape(output, [features["d_batch_size"], width])
	return output, score_sm, table, total_raw_score


def read_from_table_with_embedding(args, features, vocab_embedding, in_signal, noun):
	"""Perform attention based read from table

	Will transform table into vocab embedding space
	
	@returns read_data
	"""

	with tf.name_scope(f"read_from_{noun}"):

		table, full_width, keys_len = get_table_with_embedding(args, features, vocab_embedding, noun)

		# --------------------------------------------------------------------------
		# Read
		# --------------------------------------------------------------------------

		return read_from_table(args, features, 
			in_signal, 
			noun,
			table, 
			width=full_width, 
			keys_len=keys_len)


def read_cell(args, features, vocab_embedding, in_control_state, in_question_tokens, in_question_state):
	"""
	A read cell

	@returns read_data

	"""


	with tf.name_scope("read_cell"):

		tap_attns = []
		tap_table = None

		taps = {}
		reads = []
		attn_focus = []

		# --------------------------------------------------------------------------
		# Read data
		# --------------------------------------------------------------------------

		in_signal = []
		in_signal.append(in_control_state)

		for j in range(args["read_heads"]):
			for i in args["kb_list"]:

				in_signal_to_head = tf.concat(in_signal, -1)
				
				read, taps[i+"_attn"], table, score_raw_total = read_from_table_with_embedding(
					args, 
					features, 
					vocab_embedding, 
					in_signal_to_head, 
					noun=i
				)

				attn_focus.append(score_raw_total)

				read_words = tf.reshape(read, [features["d_batch_size"], args[i+"_width"], args["embed_width"]])	
			
				d, taps[i+"_word_attn"] = attention_by_index(in_signal_to_head, read_words)
				d = tf.concat([d, in_signal_to_head], -1)
				d = tf.layers.dense(d, args["read_width"], activation=ACTIVATION_FNS[args["read_activation"]])
				reads.append(d)
				

		reads = tf.stack(reads, axis=1)
		reads, taps["read_head_attn"] = attention_by_index(in_question_state, reads)

		# --------------------------------------------------------------------------
		# Prepare and shape results
		# --------------------------------------------------------------------------
		
		taps["read_head_attn_focus"] = tf.concat(attn_focus, -1)

		# Residual skip connection
		out_data = tf.concat([reads] + in_signal + attn_focus, -1)
		
		for i in range(args["read_layers"]):
			out_data = tf.layers.dense(out_data, args["read_width"])
			out_data = ACTIVATION_FNS[args["read_activation"]](out_data)
			
			if args["read_dropout"] > 0:
				out_data = tf.nn.dropout(out_data, 1.0-args["read_dropout"])

		return out_data, taps




