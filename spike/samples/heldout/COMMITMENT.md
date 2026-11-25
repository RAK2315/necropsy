# Held-out set: commitment

Fixed on 25 Nov 2026, before any engine work on the `format-coverage` spec began.

55 real files (TIFF 27, PBM/PGM/PPM 14, PCX 7, TGA 7) were taken unmodified from the test suites of open-source decoders that the real corpus in `spike/samples/real/` does not use. Each source is pinned to a commit and each file is under a permissive licence, read from the repository's own licence file. None of these files is byte-identical to any of the 81 files in `spike/samples/real/`.

The files and their manifest (sources, licences, header facts and what Pillow 12.2.0 does with each) are kept **outside this repository** until they are evaluated, so that the agent building the engine never reads them or tunes against them. A Kiro hook (`.kiro/hooks/heldout-guard.json`, running `python tools/heldout.py guard`) blocks any agent tool call that names the held-out folder or any held-out file.

The set is evaluated once, by Claude Code, after the `format-coverage` work is finished. The results are published as they come out, with the manifest and the files. To check that the published manifest is the one fixed here, hash it: it must match the value below, and every file must match one of the file hashes. `python tools/heldout.py verify` does both.

Manifest SHA-256: `8f840afbbc7df09d51ab222b66481ad96d73fa6aac860d5a27177bb3caed86cd`

## File SHA-256 (sorted)

- `065603f27a7d1bb34169b0d28fbbcc56363e49d6aefb3570995108b0d64bbe1e`
- `0b9b04a903b0f0d65c25900c001e16c2906acc53d90993bb7efaf1b7a1842059`
- `0efbcff0d2bc9a84e948e8d376a9965b0a13627c7f50016b0354635d0fbfa4db`
- `22286f56deccb2623895b5dc488ae9e640dfa084d03fd05ce8bd54d4074edaac`
- `25e6c060487bd2f9d0d67ff96ac69137428fff4bd2642f27997c06740597ba56`
- `26d3c60b3f660611e3b5498a8755cb051f5cf8f3ca03b18643c4d8a055288035`
- `287f1ad29c90207c0d7171b7dba84849fb04c3f60e70a75e3e046a4f58f4fb73`
- `295ec3bb98991313b10eb80d1991407b752ea8e58e5f8bebd16ec3a6ee0dcddf`
- `2a57a03d5f6fc282841fdd88027dd07c50a5c18ae4ae503372963f52e0bac1da`
- `30886fe1d685514cc5246f27a01c863a5fb99179658cfffcb99f74c8a369c661`
- `312564c51945ca1926b10f626389f79fad8fa54f584a4f0fe8bd6eba8fe660df`
- `3a016cd7f1ca6ec2cc72571ce8670a2546b15acdc7e035c329a45a8cb1717c67`
- `3b8a818cfc8a47534385d7cc74da22c86753a37a3115d87e82dd421f29f03ceb`
- `3b910c9f1be4928b6febe1dc2840c1d5f7e7fb21f409b78bcf545f77349084b0`
- `40554a4d128bab11bb5c5e9272c24b430374ae65f98f06b3abcf316a2366f91b`
- `40de3f91cad867ccda0366c984a27146bba7cccba974cc41003694cefb30bc3b`
- `4571183876961e3f74f6ac981ade0d63f11f72a6da87d967c6899bb8a2e1ef15`
- `4c438fc13d33930b110e8bf91664c5fb63170b0a40b4ac440c489252f8422777`
- `526158dc544dbee2378c8e096ff32d3f8a3b4e6dc8b0d841688535d71611cbe2`
- `52913b4034dd60357cd40a54bb9d4ee356ab28a915c6343672179e43c5551403`
- `56e7f84642770034fe1f61404f096847c61cf7773478250e03e6e6e94d8a5129`
- `59ed6e9dd19291bbdc230092ab7f6bc46fb0537ee4c9eec15dd58021cd9c12be`
- `5d0753464812d419d46cbe93a9a4910244c6e28d752349021a4ba9decef61dd7`
- `5f9af9d1d9b16549f808572264ca51a052868d1bd21aad5e8af0311699180838`
- `6017c2152db91c626c332404c7a59ae86db8db50b91d0ed09df42ba28ffe55ba`
- `6237b3ccf8b728bb15aa7dc5d222d5751ed08293dda83b2f2af96678c064dec8`
- `69b39f9fa4cae4013e7cfd9b34fd92ff5f6e2de587d3fb84c158cb8c65e3aa13`
- `6ce5fad9629cc45645ac1b9ec85b0a2441d2079db52cae86f61c6e69c9777c6f`
- `78480af87b1a4f262899c84a115f6036029f5c593a7168e9868f2ef32b33f4da`
- `7ea1f1c2dc7177091f07682c76726a61a22def13d733d77a8c6a0af6062d8cdf`
- `82c5b10d17f85e3a723aaf28b8b966263fadaa78177025ec4cbc98c50f708469`
- `8380d5420357daecede9bc933104313909548cded5c44feeb7d564884e9ce07e`
- `8c5a926059d2b15556cb7c846968fb5c9fe228e009011bdb642f74dd222a024b`
- `8d70f27c2d774c8cfc92cd2182f336e450d7498e2894fb7064fa48e014ca484f`
- `90d475d18b1b3af2dc0486bf7bce8fc20406e2559fe643ad182211da60d321b9`
- `9efe344dfc180b19b50d815d6f94aec33b936f8362f9751278d2ec2ce6d0fab5`
- `9f75418969780debe3097f0ebb92dfa0fd6efc7a41ab89ac791ba605cb43ee45`
- `9f84168caad2d837efb7267e8fda44d5fc8bccac1d94536ba15e6169554d55e6`
- `c2c044f73df7f342f4f29ad107e46ad1a836605a4e6702df7da9bf21267490ec`
- `c6834c79f4dc5ad7c9ae9b57550ab8acf66cabe0ee4eefa1990a66658e61fd83`
- `c99164f110c19423dac8d5f062c65423a905e780b05c19ed05fdbd86cd46663a`
- `cd0e95441fb8ae55be07fef946ed72a97c93b0d3ee43b9dae369c66c8a84e23c`
- `cdb0d83f62bc1c871d03f38d846c569ef710f6880b81765923e85b829c803416`
- `d9846b3065306026e127997a73275c4b9678683675fa69d73c360bf0402dd37c`
- `db6973472a25161f768a5d0bb7e1de2648ff4235d885dc05e207167d96b5e56d`
- `dd60b8737fd09774287887c2e732e0c7fabd951f1b7ccbb635d68fc77bc38075`
- `dea862b28302755f7621c2a5f72a0e6f509ecd197bfec1dbb499a44bfb2dd853`
- `e4fc59708c80c758c951a92191a388b98e6e0e50c0db8d5d741cc15e845b4359`
- `eb861709533038ecaf53a27ec4a16f909480d2f1d4a9c1690b48f426f770bd50`
- `edd011ed7bd74e5ccd3cd0b3656aefb2994b6319559ae7b124d949326a1a64fd`
- `ef568da93ff90774f33d201efa43f8645cf3f5315c7ec40af1584b20660487ba`
- `f1cfb13d87123e4646a155fe2fe7578dc2ec9e2db809f04d180acae1504db938`
- `f7b35cf16cc4ad59fb144679c6341a2622e79717ec5b0af4ae38932cf0ccad73`
- `f7cfe4c7d0f0c22dab18dda6c661525448a00dd30e8be2259a577939d5b2385d`
- `fdeac23fa991eb63ecc4b1ad245451d3cf06d6bd71ff08c8e7b5a726c7c4b9f5`
