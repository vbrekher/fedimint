from pathlib import Path

lib = Path("modules/fedimint-walletv2-server/src/lib.rs")
text = lib.read_text()

old = '''#[cfg(test)]
mod tests {
    use super::{
        MAX_PENDING_TRANSACTIONS, PendingTransactionLimitError, validate_pending_transaction_count,
    };

    #[test]
    fn pending_transaction_limit_boundary() {
        assert_eq!(
            validate_pending_transaction_count(MAX_PENDING_TRANSACTIONS),
            Ok(())
        );
        assert_eq!(
            validate_pending_transaction_count(MAX_PENDING_TRANSACTIONS + 1),
            Err(PendingTransactionLimitError)
        );
    }
}
'''

new = '''#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::time::Duration;

    use fedimint_core::bitcoin::{Block, BlockHash};
    use fedimint_core::db::mem_impl::MemDatabase;
    use fedimint_core::envs::BitcoinRpcConfig;
    use fedimint_core::module::registry::ModuleRegistry;
    use fedimint_core::task::TaskGroup;
    use fedimint_core::util::SafeUrl;
    use fedimint_core::{ChainId, Feerate, PeerId};
    use fedimint_server_core::bitcoin_rpc::{IServerBitcoinRpc, ServerBitcoinRpcMonitor};

    use super::*;

    #[derive(Debug)]
    struct MockBitcoinServerRpc;

    #[async_trait::async_trait]
    impl IServerBitcoinRpc for MockBitcoinServerRpc {
        fn get_bitcoin_rpc_config(&self) -> BitcoinRpcConfig {
            BitcoinRpcConfig {
                kind: "mock".to_string(),
                url: "http://mock".parse().expect("valid test URL"),
            }
        }

        fn get_url(&self) -> SafeUrl {
            "http://mock".parse().expect("valid test URL")
        }

        async fn get_block_count(&self) -> anyhow::Result<u64> {
            Err(anyhow::anyhow!("unused mock block count"))
        }

        async fn get_block_hash(&self, _height: u64) -> anyhow::Result<BlockHash> {
            Err(anyhow::anyhow!("unused mock block hash"))
        }

        async fn get_block(&self, _block_hash: &BlockHash) -> anyhow::Result<Block> {
            Err(anyhow::anyhow!("unused mock block"))
        }

        async fn get_feerate(&self) -> anyhow::Result<Option<Feerate>> {
            Err(anyhow::anyhow!("unused mock feerate"))
        }

        async fn submit_transaction(&self, _transaction: Transaction) -> anyhow::Result<()> {
            Ok(())
        }

        async fn get_sync_progress(&self) -> anyhow::Result<Option<f64>> {
            Err(anyhow::anyhow!("unused mock sync progress"))
        }

        async fn get_chain_id(&self) -> anyhow::Result<ChainId> {
            Ok(ChainId(BlockHash::from_byte_array([1; 32])))
        }
    }

    fn test_wallet(db: &Database, task_group: &TaskGroup) -> Wallet {
        let (bitcoin_sk, bitcoin_pk) = secp256k1::generate_keypair(&mut OsRng);
        let cfg = WalletConfig {
            private: WalletConfigPrivate { bitcoin_sk },
            consensus: WalletConfigConsensus::new(
                BTreeMap::from([(PeerId::from(0), bitcoin_pk)]),
                FeeConsensus::new(0).expect("valid fee consensus"),
                Network::Regtest,
            ),
        };

        Wallet {
            cfg,
            db: db.clone(),
            btc_rpc: ServerBitcoinRpcMonitor::new(
                MockBitcoinServerRpc.into_dyn(),
                Duration::from_secs(60),
                task_group,
            ),
        }
    }

    fn dummy_federation_tx() -> FederationTx {
        FederationTx {
            tx: Transaction {
                version: Version::TWO,
                lock_time: LockTime::ZERO,
                input: vec![],
                output: vec![],
            },
            spent_tx_outs: vec![],
            vbytes: 0,
            fee: Amount::ZERO,
        }
    }

    #[test]
    fn pending_transaction_limit_boundary() {
        assert_eq!(
            validate_pending_transaction_count(MAX_PENDING_TRANSACTIONS),
            Ok(())
        );
        assert_eq!(
            validate_pending_transaction_count(MAX_PENDING_TRANSACTIONS + 1),
            Err(PendingTransactionLimitError)
        );
    }

    #[tokio::test]
    async fn pending_transaction_limit_is_enforced_from_database() {
        let db = Database::new(MemDatabase::new(), ModuleRegistry::default());
        let task_group = TaskGroup::new();
        let wallet = test_wallet(&db, &task_group);
        let pending_tx = dummy_federation_tx();
        let mut dbtx = db.begin_transaction_nc().await;

        for index in 0..=MAX_PENDING_TRANSACTIONS {
            let txid = Txid::from_byte_array([index as u8; 32]);
            dbtx.insert_new_entry(&UnsignedTxKey(txid), &pending_tx)
                .await;
        }

        assert_eq!(
            wallet.try_consensus_fee(&mut dbtx, 1).await,
            Err(PendingTransactionLimitError)
        );
    }
}
'''

if text.count(old) != 1:
    raise SystemExit("expected the existing test module exactly once")
lib.write_text(text.replace(old, new, 1))

cargo = Path("modules/fedimint-walletv2-server/Cargo.toml")
text = cargo.read_text()
marker = 'tracing = { workspace = true }\n'
replacement = '''tracing = { workspace = true }\n\n[dev-dependencies]\ntokio = { workspace = true, features = ["macros", "rt"] }\n'''
if text.count(marker) != 1:
    raise SystemExit("expected Cargo.toml dependency footer exactly once")
cargo.write_text(text.replace(marker, replacement, 1))
