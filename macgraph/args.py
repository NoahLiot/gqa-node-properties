
import argparse
import os.path
import yaml
import pathlib
import tensorflow as tf

def absu(x):
	return tf.nn.relu(x) + tf.nn.relu(-x)

ACTIVATION_FNS = {
	"tanh": tf.tanh,
	"relu": tf.nn.relu,
	"sigmoid": tf.nn.sigmoid,
	"abs": absu,
	"id": tf.identity
}

global_args = {}


def generate_args_derivatives(args):

	r = {}
	r["modes"] = ["eval", "train", "predict"]

	# Expand input dirs
	for i in [*r["modes"], "all"]:
		r[i+"_input_path"] = os.path.join(args["input_dir"], i+"_input.tfrecords")

	r["vocab_path"] = os.path.join(args["input_dir"], "vocab.txt")
	r["config_path"] = os.path.join(args["model_dir"], "config.yaml")
	r["question_types_path"] = os.path.join(args["input_dir"], "types.yaml")
	r["answer_classes_path"] = os.path.join(args["input_dir"], "answer_classes.yaml")
	r["answer_classes_types_path"] = os.path.join(args["input_dir"], "answer_classes_types.yaml")

	if args["control_width"] is None:
		r["control_width"] = args["input_width"] * args["control_heads"]

	r["kb_list"] = ["kb_node"]

	if args["save_checkpoints_steps"] is None and args["save_checkpoints_secs"] is None:
		r["save_checkpoints_secs"] = 60 * 3

	return r



def get_args(extend=lambda parser:None, argv=None):

	parser = argparse.ArgumentParser()
	extend(parser)

	# --------------------------------------------------------------------------
	# General
	# --------------------------------------------------------------------------

	parser.add_argument('--log-level',  				type=str, default='INFO')
	parser.add_argument('--output-dir', 				type=str, default="./output")
	parser.add_argument('--input-dir',  				type=str, default="./input_data/default")
	parser.add_argument('--model-dir',      			type=str, default="./output/default")

	# Used in train / predict / build
	parser.add_argument('--limit',						type=int, default=None, help="How many rows of input data to read")
	parser.add_argument('--type-string-prefix',			type=str, default=None, help="Filter input data rows to only have this type string prefix")

	# --------------------------------------------------------------------------
	# Data build
	# --------------------------------------------------------------------------

	parser.add_argument('--eval-holdback',    			type=float, default=0.1)
	parser.add_argument('--predict-holdback', 			type=float, default=0.005)


	# --------------------------------------------------------------------------
	# Training
	# --------------------------------------------------------------------------

	parser.add_argument('--warm-start-dir',				type=str, default=None, help="Load model initial weights from previous checkpoints")
	
	parser.add_argument('--batch-size',            		type=int, default=32,   help="Number of items in a full batch")
	parser.add_argument('--max-steps',             		type=int, default=None, help="In thousands")
		
	parser.add_argument('--max-gradient-norm',     		type=float, default=0.4)
	parser.add_argument('--learning-rate',         		type=float, default=0.001)
	parser.add_argument('--save-checkpoints-steps',		type=int,	default=None, help="Passed to RunConfig in tensorflow")
	parser.add_argument('--save-checkpoints-secs',		type=int,	default=None, help="Passed to RunConfig in tensorflow")
	parser.add_argument('--throttle-secs',				type=int,	default=300, help="Passed to RunConfig in tensorflow")


	# --------------------------------------------------------------------------
	# Network topology
	# --------------------------------------------------------------------------

	parser.add_argument('--vocab-size',	           		type=int, default=128,   help="How many different words are in vocab")
	
	parser.add_argument('--max-seq-len',	  	 		type=int, default=20,   help="Maximum length of question token list")
	
	parser.add_argument('--input-layers',	   			type=int, 	default=3,    help="How many input layers are in the english encoding LSTM stack")
	parser.add_argument('--input-dropout',              type=float, default=0.2)
	parser.add_argument('--input-width',             	type=int, 	default=128)
	parser.add_argument('--disable-input-residual', 	action='store_false', dest='use_input_residual')

	parser.add_argument('--embed-width',	       		type=int, default=64,   help="The width of token embeddings")
	
	parser.add_argument('--kb-node-width',         		type=int, default=7,    help="Width of node entry into graph table aka the knowledge base")
	parser.add_argument('--kb-node-max-len',         	type=int, default=40,   help="Maximum number of nodes in kb")
	parser.add_argument('--kb-edge-width',         		type=int, default=3,    help="Width of edge entry into graph table aka the knowledge base")
	parser.add_argument('--kb-edge-max-len',         	type=int, default=40,   help="Maximum number of edges in kb")

	parser.add_argument('--read-width',         		type=int, default=128,  help="Width of the read state output")
	parser.add_argument('--read-layers',         		type=int, default=1,    help="Number of read transformation layers")
	parser.add_argument('--read-indicator-rows',        type=int, default=1,    help="Number of extra trainable rows")
	
	parser.add_argument('--control-width',	           	type=int, default=None,	help="The width of control state")
	parser.add_argument('--control-heads',	           	type=int, default=2,	help="The number of control question-word attention heads")
	parser.add_argument('--control-dropout',	        type=float, default=0.0, help="Dropout on the control unit")

	parser.add_argument('--output-activation',			type=str, default="id", choices=ACTIVATION_FNS.keys())
	parser.add_argument('--output-layers',				type=int, default=2)
	parser.add_argument('--output-classes',	       		type=int, default=128,    help="The number of different possible answers (e.g. answer classes). Currently tied to vocab size since we attempt to tokenise the output.")

	parser.add_argument('--disable-control-cell', 		action='store_false', dest="use_control_cell")
	parser.add_argument('--disable-output-cell', 		action='store_false', dest="use_output_cell")
	parser.add_argument('--disable-output-read', 		action='store_false', dest="use_output_read")
	parser.add_argument('--disable-dynamic-decode', 	action='store_false', dest="use_dynamic_decode")
	parser.add_argument('--enable-question-state', 		action='store_true', dest="use_question_state")

	parser.add_argument('--enable-tf-debug', 			action='store_true',  dest="use_tf_debug")
	parser.add_argument('--disable-summary-scalar', 	action='store_false', dest='use_summary_scalar')
	parser.add_argument('--disable-summary-image', 		action='store_false', dest='use_summary_image')

	parser.add_argument('--max-decode-iterations', 		type=int, default=1)
	
	args = vars(parser.parse_args(argv))

	args.update(generate_args_derivatives(args))
	
	# Global singleton var for easy access deep in the codebase (e.g. utility functions)
	# Note that this wont play well with PBT!! 
	# TODO: Remove
	global_args.clear()
	global_args.update(args)

	return args


def save_args(args):
	pathlib.Path(args["model_dir"]).mkdir(parents=True, exist_ok=True)
	with tf.gfile.GFile(os.path.join(args["config_path"]), "w") as file:
		yaml.dump(args, file)
